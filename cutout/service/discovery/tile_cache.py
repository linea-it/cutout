"""Resident spatial tile indexes shared by discovery requests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

import numpy as np

T = TypeVar("T")

_lock = threading.Lock()
_row_cache: dict[tuple[str, int, int], list] = {}
_index_cache: dict[tuple[str, int, int], SpatialTileIndex] = {}


@dataclass(frozen=True)
class SpatialTileIndex(Generic[T]):
    """Tile metadata plus numeric bounds queried with vectorized comparisons."""

    records: tuple[T, ...]
    ra_min: np.ndarray
    ra_max: np.ndarray
    dec_min: np.ndarray
    dec_max: np.ndarray

    def matching_indices(self, *, ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> np.ndarray:
        dec_overlap = (self.dec_min <= dec_max) & (self.dec_max >= dec_min)
        ra_overlap = (self.ra_min <= ra_max) & (self.ra_max >= ra_min)
        wraps_tile = self.ra_max > 360
        ra_overlap |= wraps_tile & ((self.ra_min - 360) <= ra_max) & ((self.ra_max - 360) >= ra_min)
        if ra_min < 0:
            ra_overlap |= (self.ra_min <= (ra_max + 360)) & (self.ra_max >= (ra_min + 360))
        return np.flatnonzero(dec_overlap & ra_overlap)


def _cache_key(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def cached_tile_rows(path: Path, loader: Callable[[Path], list[T]]) -> list[T]:
    key = _cache_key(path)
    hit = _row_cache.get(key)
    if hit is not None:
        return hit

    rows = loader(path)
    with _lock:
        _row_cache[key] = rows
        for old in [item for item in _row_cache if item[0] == key[0] and item != key]:
            del _row_cache[old]
    return rows


def cached_spatial_index(
    path: Path,
    loader: Callable[[Path], list[T]],
    bounds: Callable[[T], tuple[float, float, float, float]],
) -> SpatialTileIndex[T]:
    key = _cache_key(path)
    hit = _index_cache.get(key)
    if hit is not None:
        return hit

    records = tuple(loader(path))
    values = np.asarray([bounds(record) for record in records], dtype=np.float64)
    if not records:
        values = np.empty((0, 4), dtype=np.float64)
    index = SpatialTileIndex(
        records=records,
        ra_min=values[:, 0],
        ra_max=values[:, 1],
        dec_min=values[:, 2],
        dec_max=values[:, 3],
    )
    with _lock:
        _index_cache[key] = index
        for old in [item for item in _index_cache if item[0] == key[0] and item != key]:
            del _index_cache[old]
    return index
