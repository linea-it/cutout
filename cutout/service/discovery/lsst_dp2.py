"""LSST DP2 coadd discovery.

Same ``deep_coadd_{tract}_{patch}_{band}_*.fits`` layout as DP1. The shipped
``lsst_dp2.csv`` is the sky index; ``build_tile_csv`` rebuilds it from the
FITS tree mounted at ``/data/tiles/lsst_dp2``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cutout.service.surveys import LSST_DP2_ID

from .lsst_dp1 import LsstDp1FileLocator
from .lsst_dp1 import build_tile_csv as _build_dp1_tile_csv

DEFAULT_TILE_LIST = Path("/app/cutout/service/discovery/lsst_dp2.csv")
DEFAULT_TILES_ROOT = Path("/data/tiles/lsst_dp2")
SURVEY_IDS = frozenset({LSST_DP2_ID})


@dataclass
class LsstDp2FileLocator(LsstDp1FileLocator):
    survey_ids = SURVEY_IDS
    tile_list_path: Path = DEFAULT_TILE_LIST
    tiles_root: Path = DEFAULT_TILES_ROOT


def build_tile_csv(
    tiles_root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    return _build_dp1_tile_csv(
        tiles_root or DEFAULT_TILES_ROOT,
        output_path or DEFAULT_TILE_LIST,
    )
