from pathlib import Path

from cutout.service.discovery.tile_cache import cached_spatial_index, cached_tile_rows


def test_cached_tile_rows_loads_once_until_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "tiles.csv"
    path.write_text("a\n", encoding="utf-8")
    calls = {"n": 0}

    def load(csv_path: Path) -> list[str]:
        calls["n"] += 1
        return csv_path.read_text(encoding="utf-8").splitlines()

    first = cached_tile_rows(path, load)
    second = cached_tile_rows(path, load)

    assert first == second == ["a"]
    assert calls["n"] == 1

    path.write_text("a\nbb\n", encoding="utf-8")
    third = cached_tile_rows(path, load)

    assert third == ["a", "bb"]
    assert calls["n"] == 2


def test_spatial_index_matches_tiles_across_ra_zero(tmp_path: Path) -> None:
    path = tmp_path / "tiles.csv"
    path.write_text("tiles\n", encoding="utf-8")
    rows = [
        ("normal", 10.0, 11.0, -1.0, 1.0),
        ("wraps", 359.9, 360.1, -1.0, 1.0),
        ("far", 20.0, 21.0, -1.0, 1.0),
    ]

    index = cached_spatial_index(path, lambda _path: rows, lambda row: row[1:])

    wrap_indices = index.matching_indices(ra_min=-0.1, ra_max=0.1, dec_min=-0.2, dec_max=0.2)
    edge_indices = index.matching_indices(ra_min=10.5, ra_max=10.5, dec_min=0, dec_max=0)

    assert [index.records[i][0] for i in wrap_indices] == ["wraps"]
    assert [index.records[i][0] for i in edge_indices] == ["normal"]


def test_spatial_index_handles_an_empty_csv(tmp_path: Path) -> None:
    path = tmp_path / "tiles.csv"
    path.write_text("", encoding="utf-8")

    index = cached_spatial_index(path, lambda _path: [], lambda row: row)

    assert index.matching_indices(ra_min=0, ra_max=1, dec_min=0, dec_max=1).size == 0
