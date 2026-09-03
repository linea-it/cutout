import pytest
from django.contrib.auth.models import AnonymousUser, Group

from cutout.service.policies import (
    DesDr2AccessPolicy,
    LsstDp1AccessPolicy,
    can_request_cutout,
    get_survey_access_policy,
)
from cutout.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_des_dr2_policy_allows_anonymous() -> None:
    policy = DesDr2AccessPolicy()
    assert policy.can_request_cutout(user=UserFactory(), survey_id="des_dr2") is True
    assert policy.can_request_cutout(user=AnonymousUser(), survey_id="des_dr2") is True
    assert policy.can_request_cutout(user=None, survey_id="des_dr2") is True
    assert policy.can_request_cutout(user=None, survey_id="lsst_dp2") is False


def test_lsst_dp1_policy_requires_group() -> None:
    policy = LsstDp1AccessPolicy()
    user = UserFactory()
    assert policy.can_request_cutout(user=user, survey_id="lsst_dp1") is False
    group, _ = Group.objects.get_or_create(name="lsst_dp1")
    user.groups.add(group)
    assert policy.can_request_cutout(user=user, survey_id="lsst_dp1") is True


def test_policy_registry_dispatches_by_survey() -> None:
    assert isinstance(get_survey_access_policy("des_dr2"), DesDr2AccessPolicy)
    assert get_survey_access_policy("lsst_dp2") is None
    assert get_survey_access_policy("lsst_dp02") is None
    assert isinstance(get_survey_access_policy("lsst_dp1"), LsstDp1AccessPolicy)
    assert get_survey_access_policy("private_survey") is None


def test_can_request_cutout_denies_unknown_survey() -> None:
    assert can_request_cutout(user=UserFactory(), survey_id="private_survey") is False
    assert can_request_cutout(user=None, survey_id="des_dr2") is True
