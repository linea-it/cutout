import pytest

from cutout.service.bands import assert_result_path


def test_assert_result_path_accepts_under_results_root(tmp_path, monkeypatch):
    monkeypatch.setattr("cutout.service.bands.get_results_root", lambda: tmp_path)
    target = tmp_path / "sync" / "out.fits"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"ok")

    assert assert_result_path(target) == target.resolve()


def test_assert_result_path_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr("cutout.service.bands.get_results_root", lambda: tmp_path / "results")
    (tmp_path / "results").mkdir()
    outside = tmp_path / "tiles" / "secret.fits"
    outside.parent.mkdir()
    outside.write_bytes(b"nope")

    with pytest.raises(ValueError, match="escapes results root"):
        assert_result_path(outside)
