import pytest

from cutout.service.discovery import DesDr2FileLocator, LsstDp1FileLocator, LsstDp2FileLocator, get_file_locator


def test_get_file_locator_returns_des_dr2() -> None:
    locator = get_file_locator("des_dr2")
    assert isinstance(locator, DesDr2FileLocator)


def test_get_file_locator_returns_lsst_dp1() -> None:
    locator = get_file_locator("lsst_dp1")
    assert isinstance(locator, LsstDp1FileLocator)
    assert locator.tiles_root.as_posix().endswith("lsst_dp1")


def test_get_file_locator_returns_lsst_dp2() -> None:
    locator = get_file_locator("lsst_dp2")
    assert isinstance(locator, LsstDp2FileLocator)
    assert locator.tiles_root.as_posix().endswith("lsst_dp2")
    assert locator.tile_list_path.as_posix().endswith("lsst_dp2.csv")


def test_get_file_locator_rejects_unknown_survey() -> None:
    with pytest.raises(ValueError, match="Unsupported survey_id"):
        get_file_locator("des_dr2_unknown")
