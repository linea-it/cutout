from pathlib import Path

from cutout.service.discovery.lsst_dp2 import COADD_SUFFIX, LsstDp2FileLocator
from cutout.service.stencils import CircleStencil


def test_empty_index_returns_no_files(tmp_path: Path) -> None:
    csv_path = tmp_path / "lsst_dp2.csv"
    csv_path.write_text("tract;patch;rall;decll;raur;decur\n", encoding="utf-8")
    locator = LsstDp2FileLocator(tile_list_path=csv_path, tiles_root=tmp_path)
    stencil = CircleStencil.from_string("53  -28 0.5")
    assert locator.find_files(survey_id="lsst_dp2", stencil=stencil, band="g") == []


def test_find_files_builds_band_path(tmp_path: Path) -> None:
    csv_path = tmp_path / "lsst_dp2.csv"
    csv_path.write_text(
        "tract;patch;rall;decll;raur;decur\n5525;10;10.0;-1.0;12.0;1.0\n",
        encoding="utf-8",
    )
    band_dir = tmp_path / "g"
    band_dir.mkdir()
    expected = band_dir / f"deep_coadd_5525_10_g_{COADD_SUFFIX}"
    expected.write_bytes(b"")
    locator = LsstDp2FileLocator(tile_list_path=csv_path, tiles_root=tmp_path)
    stencil = CircleStencil.from_string("11 0 0.5")

    files = locator.find_files(survey_id="lsst_dp2", stencil=stencil, band="g")

    assert [f.tile_id for f in files] == ["5525/10"]
    assert files[0].file_path == expected.resolve()


def test_missing_coadd_returns_no_path(tmp_path: Path) -> None:
    csv_path = tmp_path / "lsst_dp2.csv"
    csv_path.write_text(
        "tract;patch;rall;decll;raur;decur\n5525;10;10.0;-1.0;12.0;1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "g").mkdir()
    locator = LsstDp2FileLocator(tile_list_path=csv_path, tiles_root=tmp_path)
    stencil = CircleStencil.from_string("11 0 0.5")

    files = locator.find_files(survey_id="lsst_dp2", stencil=stencil, band="g")

    assert [f.tile_id for f in files] == ["5525/10"]
    assert files[0].file_path is None
