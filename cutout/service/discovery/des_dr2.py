from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from cutout.service.bands import assert_path_under_root, assert_safe_band, assert_safe_path_component
from cutout.service.stencils import Stencil
from cutout.service.surveys import DES_DR2_ID

from .base import FileLocator
from .models import FileDescriptor

DEFAULT_TILE_LIST = Path("/app/cutout/service/discovery/dr2_tiles.csv")
DEFAULT_TILES_ROOT = Path("/data/tiles/des_dr2")
CSV_FIELDS = ("tilename", "rall", "decll", "raur", "decur", "archive_path")
SURVEY_IDS = frozenset({DES_DR2_ID})


@dataclass(frozen=True)
class _TileBounds:
    tile_id: str
    ra_min: float
    ra_max: float
    dec_min: float
    dec_max: float
    archive_path: str


@dataclass
class DesDr2FileLocator(FileLocator):
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

        try:
            for tile in self._read_tiles():
                if not self._intersects(tile, ra_min=ra_min, ra_max=ra_max, dec_min=dec_min, dec_max=dec_max):
                    continue

                print("Achou uma tile")
                print(tile)
                descriptor = FileDescriptor(
                    tile_id=tile.tile_id,
                    archive_path=tile.archive_path,
                    file_path=self._build_file_path(tile.archive_path, band),
                    band=band,
                )
                print(descriptor)
                descriptors.append(descriptor)
        except Exception as e:
            print(f"[DesDr2FileLocator.find_files] Error while finding files: {e}")
            raise
        return descriptors

    def _read_tiles(self) -> list[_TileBounds]:
        rows: list[_TileBounds] = []
        with self.tile_list_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if not all(key in row for key in CSV_FIELDS):
                    print(f"[DesDr2FileLocator._read_tiles] Skipping row due to missing keys: {row}")
                    continue
                rows.append(
                    _TileBounds(
                        tile_id=row["tilename"],
                        ra_min=float(row["rall"]),
                        dec_min=float(row["decll"]),
                        ra_max=float(row["raur"]),
                        dec_max=float(row["decur"]),
                        archive_path=row.get("archive_path"),
                    )
                )

        print(f"[DesDr2FileLocator._read_tiles] read {len(rows)} tiles from {self.tile_list_path}")
        return rows

    @staticmethod
    def _intersects(tile: _TileBounds, *, ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> bool:
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

    def _build_file_path(self, archive_path: str, band: str | None) -> Path | None:
        if not band:
            return None
        band = assert_safe_band(band)
        if not archive_path:
            raise ValueError("Missing archive_path")

        parts = archive_path.split("/")
        if len(parts) < 4:
            raise ValueError(f"Malformed archive_path: {archive_path!r}")

        run = assert_safe_path_component(parts[1], label="run")
        tilename = assert_safe_path_component(parts[2], label="tilename")
        process = assert_safe_path_component(parts[3], label="process")

        filename = f"{tilename}_{run}{process}_{band}.fits.fz"
        candidate = self.tiles_root.joinpath(tilename).joinpath(filename)
        # Leaf files under des_dr2 are often symlinks into Y6A1; do not follow them
        # for the containment check (still blocks .. traversal via resolved parents).
        return assert_path_under_root(
            candidate,
            self.tiles_root,
            label="tiles root",
            follow_symlinks=False,
        )
