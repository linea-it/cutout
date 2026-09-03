from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS

from cutout.service.bands import assert_path_under_root, assert_safe_band, assert_safe_path_component
from cutout.service.stencils import Stencil
from cutout.service.surveys import LSST_DP1_ID

from .base import FileLocator
from .models import FileDescriptor

DEFAULT_TILE_LIST = Path("/app/cutout/service/discovery/lsst_dp1.csv")
DEFAULT_TILES_ROOT = Path("/data/tiles/lsst_dp1")
CSV_FIELDS = ("tract", "patch", "rall", "decll", "raur", "decur")
SURVEY_IDS = frozenset({LSST_DP1_ID})
BANDS = ("u", "g", "r", "i", "z", "y")


@dataclass(frozen=True)
class _PatchBounds:
    tract: str
    patch: str
    ra_min: float
    ra_max: float
    dec_min: float
    dec_max: float

    @property
    def tile_id(self) -> str:
        return f"{self.tract}/{self.patch}"


def _parse_deep_coadd_name(name: str) -> tuple[str, str, str] | None:
    """Parse ``deep_coadd_{tract}_{patch}_{band}_....fits``."""
    if not name.startswith("deep_coadd_") or not name.endswith(".fits"):
        return None
    parts = name.split("_")
    if len(parts) < 5:
        return None
    tract, patch, band = parts[2], parts[3], parts[4]
    if not tract or not patch or not band:
        return None
    return tract, patch, band


def _iter_band_files(tiles_root: Path) -> dict[tuple[str, str], Path]:
    """Union of ``(tract, patch)`` across every band directory.

    A patch present only in ``u`` (or any other band) is still indexed.
    One representative FITS is kept per key (first band that has the file).
    """
    by_patch: dict[tuple[str, str], Path] = {}
    for band in BANDS:
        band_dir = tiles_root / band
        if not band_dir.is_dir():
            continue
        for path in band_dir.glob("deep_coadd_*_*_*_*.fits"):
            parsed = _parse_deep_coadd_name(path.name)
            if parsed is None:
                continue
            tract, patch, _band = parsed
            by_patch.setdefault((tract, patch), path)
    return by_patch


def _science_hdu(hdul: fits.HDUList):
    for hdu in hdul:
        header = getattr(hdu, "header", None)
        if header is None:
            continue
        if int(header.get("NAXIS", 0) or 0) >= 2:
            return hdu
    return hdul[0]


def _fits_aabb(path: Path) -> tuple[float, float, float, float]:
    """RA/Dec axis-aligned box from WCS header only (no image data)."""
    with fits.open(path, memmap=True) as hdul:
        hdu = _science_hdu(hdul)
        header = hdu.header
        nx = int(header["NAXIS1"])
        ny = int(header["NAXIS2"])
        wcs = WCS(header)
    corners = wcs.wcs_pix2world(
        [[0.5, 0.5], [nx + 0.5, 0.5], [0.5, ny + 0.5], [nx + 0.5, ny + 0.5]],
        1,
    )
    ras = corners[:, 0]
    decs = corners[:, 1]
    return float(ras.min()), float(decs.min()), float(ras.max()), float(decs.max())


def build_tile_csv(
    tiles_root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Scan all band folders and write ``tract;patch;rall;decll;raur;decur``."""
    tiles_root = Path(tiles_root or DEFAULT_TILES_ROOT)
    output_path = Path(output_path or DEFAULT_TILE_LIST)
    by_patch = _iter_band_files(tiles_root)
    rows = []
    for (tract, patch), path in sorted(by_patch.items(), key=lambda item: (int(item[0][0]), int(item[0][1]))):
        rall, decll, raur, decur = _fits_aabb(path)
        rows.append(
            {
                "tract": tract,
                "patch": patch,
                "rall": rall,
                "decll": decll,
                "raur": raur,
                "decur": decur,
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return output_path


@dataclass
class LsstDp1FileLocator(FileLocator):
    survey_ids = SURVEY_IDS
    tile_list_path: Path = DEFAULT_TILE_LIST
    tiles_root: Path = DEFAULT_TILES_ROOT

    def find_files(
        self,
        *,
        survey_id: str,
        stencil: Stencil,
        band: str | None = None,
    ) -> list[FileDescriptor]:
        if survey_id not in self.survey_ids:
            raise ValueError(f"Unsupported survey_id: {survey_id}")

        ra_min, ra_max, dec_min, dec_max = stencil.axis_aligned_bounds()
        descriptors: list[FileDescriptor] = []
        for tile in self._read_tiles():
            if not self._intersects(tile, ra_min=ra_min, ra_max=ra_max, dec_min=dec_min, dec_max=dec_max):
                continue
            descriptors.append(
                FileDescriptor(
                    tile_id=tile.tile_id,
                    archive_path=f"{tile.tract}/{tile.patch}",
                    file_path=self._build_file_path(tile.tract, tile.patch, band),
                    band=band,
                )
            )
        return descriptors

    def _read_tiles(self) -> list[_PatchBounds]:
        rows: list[_PatchBounds] = []
        with self.tile_list_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            for row in reader:
                if not all(key in row for key in CSV_FIELDS):
                    continue
                rows.append(
                    _PatchBounds(
                        tract=row["tract"],
                        patch=row["patch"],
                        ra_min=float(row["rall"]),
                        dec_min=float(row["decll"]),
                        ra_max=float(row["raur"]),
                        dec_max=float(row["decur"]),
                    )
                )
        return rows

    @staticmethod
    def _intersects(tile: _PatchBounds, *, ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> bool:
        dec_overlap = tile.dec_min <= dec_max and tile.dec_max >= dec_min
        if not dec_overlap:
            return False
        ra_overlap = tile.ra_min <= ra_max and tile.ra_max >= ra_min
        if ra_overlap:
            return True
        if tile.ra_max > 360:
            ra_overlap = (tile.ra_min - 360) <= ra_max and (tile.ra_max - 360) >= ra_min
        if not ra_overlap and ra_min < 0:
            ra_overlap = tile.ra_min <= (ra_max + 360) and tile.ra_max >= (ra_min + 360)
        return ra_overlap

    def _build_file_path(self, tract: str, patch: str, band: str | None) -> Path | None:
        if not band:
            return None
        band = assert_safe_band(band)
        tract = assert_safe_path_component(tract, label="tract")
        patch = assert_safe_path_component(patch, label="patch")
        band_dir = self.tiles_root / band
        matches = sorted(band_dir.glob(f"deep_coadd_{tract}_{patch}_{band}_*.fits"))
        if not matches:
            return None
        return assert_path_under_root(
            matches[0],
            self.tiles_root,
            label="tiles root",
            follow_symlinks=False,
        )
