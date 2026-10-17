from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from cutout.service.bands import assert_path_under_root, assert_safe_band, assert_safe_path_component
from cutout.service.stencils import Stencil
from cutout.service.surveys import DES_DR2_ID

from .base import FileLocator
from .models import FileDescriptor
from .tile_cache import SpatialTileIndex, cached_spatial_index

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


def _load_des_tiles(path: Path) -> list[_TileBounds]:
    rows: list[_TileBounds] = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=";")
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
    print(f"[DesDr2FileLocator._read_tiles] read {len(rows)} tiles from {path}")
    return rows


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

        return self._descriptors(self._matching_tiles(stencil), band)

    def find_files_for_bands(
        self,
        *,
        survey_id: str,
        stencil: Stencil,
        bands: list[str],
    ) -> dict[str, list[FileDescriptor]]:
        if survey_id not in self.survey_ids:
            raise ValueError(f"Unsupported survey_id: {survey_id}")

        tiles = self._matching_tiles(stencil)
        return {band: self._descriptors(tiles, band) for band in bands}

    def _matching_tiles(self, stencil: Stencil) -> list[_TileBounds]:
        tiles = self._tile_index()
        ra_min, ra_max, dec_min, dec_max = stencil.axis_aligned_bounds()
        return [
            tiles.records[index]
            for index in tiles.matching_indices(ra_min=ra_min, ra_max=ra_max, dec_min=dec_min, dec_max=dec_max)
        ]

    def _descriptors(self, tiles: list[_TileBounds], band: str | None) -> list[FileDescriptor]:
        descriptors: list[FileDescriptor] = []
        for tile in tiles:
            descriptors.append(
                FileDescriptor(
                    tile_id=tile.tile_id,
                    archive_path=tile.archive_path,
                    file_path=self._build_file_path(tile.archive_path, band),
                    band=band,
                )
            )
        return descriptors

    def _tile_index(self) -> SpatialTileIndex[_TileBounds]:
        return cached_spatial_index(
            self.tile_list_path,
            _load_des_tiles,
            lambda tile: (tile.ra_min, tile.ra_max, tile.dec_min, tile.dec_max),
        )

    def preload(self) -> None:
        self._tile_index()

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
