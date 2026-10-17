"""LSST DP2 coadd discovery.

Same layout as DP1: ``{band}/deep_coadd_{tract}_{patch}_{band}_{suffix}``.
Tract and patch come from the sky index; the release suffix is fixed.
``build_tile_csv`` rebuilds the index from ``/data/tiles/lsst_dp2``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cutout.service.surveys import LSST_DP2_ID

from .lsst_dp1 import LsstDp1FileLocator
from .lsst_dp1 import build_tile_csv as _build_dp1_tile_csv

DEFAULT_TILE_LIST = Path("/app/cutout/service/discovery/lsst_dp2.csv")
DEFAULT_TILES_ROOT = Path("/data/tiles/lsst_dp2")
COADD_SUFFIX = "lsst_cells_v2_LSSTCam_runs_DRP_DP2_v30_0_8_DM-55060_deep_coadd_rewrite_20260618T031503Z.fits"
SURVEY_IDS = frozenset({LSST_DP2_ID})


@dataclass
class LsstDp2FileLocator(LsstDp1FileLocator):
    survey_ids = SURVEY_IDS
    tile_list_path: Path = DEFAULT_TILE_LIST
    tiles_root: Path = DEFAULT_TILES_ROOT
    coadd_suffix: str = COADD_SUFFIX


def build_tile_csv(
    tiles_root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    return _build_dp1_tile_csv(
        tiles_root or DEFAULT_TILES_ROOT,
        output_path or DEFAULT_TILE_LIST,
    )
