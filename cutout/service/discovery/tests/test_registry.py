import pytest

from cutout.service.discovery import DesDr2FileLocator, LsstDp1FileLocator, get_file_locator


def test_get_file_locator_returns_des_dr2() -> None:
    locator = get_file_locator("des_dr2")
    assert isinstance(locator, DesDr2FileLocator)


def test_get_file_locator_returns_lsst_dp1() -> None:
    locator = get_file_locator("lsst_dp1")
    assert isinstance(locator, LsstDp1FileLocator)


def test_get_file_locator_rejects_unknown_survey() -> None:
    with pytest.raises(ValueError, match="Unsupported survey_id"):
        get_file_locator("des_dr2_unknown")
