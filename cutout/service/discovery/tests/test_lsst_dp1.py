from pathlib import Path

from cutout.service.discovery.lsst_dp1 import LsstDp1FileLocator, _iter_band_files
from cutout.service.stencils import CircleStencil

SUFFIX = "lsst_cells_v1_LSSTComCam_runs_DRP_DP1_DM-51335.fits"


def _touch(root: Path, band: str, tract: str, patch: str) -> Path:
    band_dir = root / band
    band_dir.mkdir(parents=True, exist_ok=True)
    path = band_dir / f"deep_coadd_{tract}_{patch}_{band}_{SUFFIX}"
    path.write_bytes(b"")
    return path


def test_iter_band_files_unions_patches_missing_from_g(tmp_path: Path) -> None:
    """A tract/patch only in u or y must still enter the index."""
    _touch(tmp_path, "g", "5525", "10")
    _touch(tmp_path, "r", "5525", "10")
    only_u = _touch(tmp_path, "u", "453", "84")
    only_y = _touch(tmp_path, "y", "10704", "11")

    by_patch = _iter_band_files(tmp_path)

    assert set(by_patch) == {("5525", "10"), ("453", "84"), ("10704", "11")}
    assert by_patch[("453", "84")] == only_u
    assert by_patch[("10704", "11")] == only_y


def test_find_files_builds_band_path(tmp_path: Path) -> None:
    csv_path = tmp_path / "lsst_dp1.csv"
    csv_path.write_text(
        "tract;patch;rall;decll;raur;decur\n" "5525;10;10.0;-1.0;12.0;1.0\n",
        encoding="utf-8",
    )
    expected = _touch(tmp_path, "g", "5525", "10")
    locator = LsstDp1FileLocator(tile_list_path=csv_path, tiles_root=tmp_path)
    stencil = CircleStencil.from_string("11 0 0.5")

    files = locator.find_files(survey_id="lsst_dp1", stencil=stencil, band="g")

    assert [f.tile_id for f in files] == ["5525/10"]
    assert files[0].file_path == expected.resolve()
