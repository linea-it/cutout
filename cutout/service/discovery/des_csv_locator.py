from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from cutout.service.stencils import CircleStencil, PolygonStencil, RangeStencil, Stencil

from .base import FileLocator
from .models import FileDescriptor


@dataclass(frozen=True)
class _TileBounds:
    tile_id: str
    ra_min: float
    ra_max: float
    dec_min: float
    dec_max: float
    archive_path: str


class DesCsvFileLocator(FileLocator):
    def __init__(self, tile_list_path: Path | None = None, tiles_root: Path | None = None) -> None:
        self._tile_list_path = tile_list_path or Path("/app/cutout/lib/dr2_tiles.csv")
        self._tiles_root = tiles_root or Path("/data/tiles")

    def find_files(
        self,
        *,
        survey_id: str,
        stencil: Stencil,
        band: str | None = None,
    ) -> list[FileDescriptor]:
        if survey_id != "des_dr2":
            raise ValueError(f"Unsupported survey_id: {survey_id}")

        ra_min, ra_max, dec_min, dec_max = self._stencil_to_bounds(stencil)
        descriptors: list[FileDescriptor] = []

        for tile in self._read_tiles():
            if not self._intersects(tile, ra_min=ra_min, ra_max=ra_max, dec_min=dec_min, dec_max=dec_max):
                continue
            descriptors.append(
                FileDescriptor(
                    tile_id=tile.tile_id,
                    archive_path=tile.archive_path,
                    file_path=self._build_file_path(tile.archive_path, band),
                    band=band,
                )
            )

        return descriptors

    def _read_tiles(self) -> list[_TileBounds]:
        rows: list[_TileBounds] = []
        with self._tile_list_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                rows.append(
                    _TileBounds(
                        tile_id=row["tilename"],
                        ra_min=float(row["rall"]),
                        dec_min=float(row["decll"]),
                        ra_max=float(row["raur"]),
                        dec_max=float(row["decur"]),
                        archive_path=row["archive_path"],
                    )
                )
        return rows

    @staticmethod
    def _intersects(tile: _TileBounds, *, ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> bool:
        ra_overlap = tile.ra_min <= ra_max and tile.ra_max >= ra_min
        dec_overlap = tile.dec_min <= dec_max and tile.dec_max >= dec_min
        return ra_overlap and dec_overlap

    @staticmethod
    def _stencil_to_bounds(stencil: Stencil) -> tuple[float, float, float, float]:
        if isinstance(stencil, CircleStencil):
            ra = stencil.center.ra.degree
            dec = stencil.center.dec.degree
            radius = stencil.radius.degree
            return (ra - radius, ra + radius, dec - radius, dec + radius)

        if isinstance(stencil, RangeStencil):
            ra_min, ra_max = stencil.ra
            dec_min, dec_max = stencil.dec
            return (ra_min, ra_max, dec_min, dec_max)

        if isinstance(stencil, PolygonStencil):
            ras = stencil.vertices.ra.degree
            decs = stencil.vertices.dec.degree
            return (float(min(ras)), float(max(ras)), float(min(decs)), float(max(decs)))

        raise ValueError(f"Unsupported stencil type: {type(stencil).__name__}")

    def _build_file_path(self, archive_path: str, band: str | None) -> Path | None:
        if not band:
            return None

        parts = archive_path.split("/")
        filename = f"{parts[2]}_{parts[1]}{parts[3]}_{band}.fits.fz"
        return self._tiles_root.joinpath(archive_path).joinpath(filename)
