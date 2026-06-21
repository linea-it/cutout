from pathlib import Path

from cutout.service.discovery.des_csv_locator import DesCsvFileLocator
from cutout.service.stencils import CircleStencil, PolygonStencil, RangeStencil

CSV_CONTENT = """tilename;rall;decll;raur;decur;archive_path
TILE_A;9.0;-1.0;11.0;1.0;Y6A1/r4907/TILE_A/p01/coadd
TILE_B;11.0;-1.0;13.0;1.0;Y6A1/r4907/TILE_B/p01/coadd
TILE_C;19.0;19.0;21.0;21.0;Y6A1/r4907/TILE_C/p01/coadd
"""


def _make_locator(tmp_path: Path) -> DesCsvFileLocator:
    tiles_file = tmp_path / "tiles.csv"
    tiles_file.write_text(CSV_CONTENT, encoding="utf-8")
    return DesCsvFileLocator(tile_list_path=tiles_file, tiles_root=Path("/data/tiles"))


def test_find_files_circle_returns_intersecting_tiles(tmp_path: Path) -> None:
    locator = _make_locator(tmp_path)
    stencil = CircleStencil.from_string("10.5 0 1")

    files = locator.find_files(survey_id="des_dr2", stencil=stencil, band="g")

    assert [f.tile_id for f in files] == ["TILE_A", "TILE_B"]
    assert str(files[0].file_path).endswith("/Y6A1/r4907/TILE_A/p01/coadd/TILE_A_r4907p01_g.fits.fz")


def test_find_files_range_returns_single_tile(tmp_path: Path) -> None:
    locator = _make_locator(tmp_path)
    stencil = RangeStencil.from_string("19.4 19.8 19.4 19.8")

    files = locator.find_files(survey_id="des_dr2", stencil=stencil, band="r")

    assert [f.tile_id for f in files] == ["TILE_C"]


def test_find_files_polygon_returns_intersecting_tiles(tmp_path: Path) -> None:
    locator = _make_locator(tmp_path)
    stencil = PolygonStencil.from_string("10 -0.5 12 -0.5 12 0.5 10 0.5")

    files = locator.find_files(survey_id="des_dr2", stencil=stencil, band="i")

    assert [f.tile_id for f in files] == ["TILE_A", "TILE_B"]


def test_find_files_rejects_unknown_survey(tmp_path: Path) -> None:
    locator = _make_locator(tmp_path)
    stencil = CircleStencil.from_string("10.5 0 1")

    try:
        locator.find_files(survey_id="unknown", stencil=stencil, band="g")
    except ValueError as exc:
        assert "Unsupported survey_id" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported survey")


def test_find_files_no_overlap_returns_empty_list(tmp_path: Path) -> None:
    locator = _make_locator(tmp_path)
    stencil = CircleStencil.from_string("100 50 0.1")

    files = locator.find_files(survey_id="des_dr2", stencil=stencil, band="g")

    assert files == []
