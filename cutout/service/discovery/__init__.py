from .base import FileLocator
from .des_dr2 import DesDr2FileLocator
from .lsst_dp1 import LsstDp1FileLocator
from .lsst_dp1 import build_tile_csv as build_dp1_tile_csv
from .lsst_dp2 import LsstDp2FileLocator
from .lsst_dp2 import build_tile_csv as build_dp2_tile_csv
from .models import FileDescriptor
from .registry import get_file_locator

# DP1 name kept for existing callers.
build_tile_csv = build_dp1_tile_csv

__all__ = [
    "DesDr2FileLocator",
    "FileDescriptor",
    "FileLocator",
    "LsstDp1FileLocator",
    "LsstDp2FileLocator",
    "build_dp1_tile_csv",
    "build_dp2_tile_csv",
    "build_tile_csv",
    "get_file_locator",
]
