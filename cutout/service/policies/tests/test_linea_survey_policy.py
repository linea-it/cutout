import pytest
from django.contrib.auth.models import AnonymousUser, Group

from cutout.service.policies import LineaSurveyAccessPolicy
from cutout.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_linea_survey_policy_allows_des_dr2_without_group() -> None:
    policy = LineaSurveyAccessPolicy()
    user = UserFactory()

    assert policy.can_request_cutout(user=user, survey_id="des_dr2") is True
    assert policy.can_request_cutout(user=AnonymousUser(), survey_id="des_dr2") is True
    assert policy.can_request_cutout(user=None, survey_id="des_dr2") is True


def test_linea_survey_policy_denies_unknown_survey() -> None:
    policy = LineaSurveyAccessPolicy()
    user = UserFactory()

    assert policy.can_request_cutout(user=user, survey_id="private_survey") is False


def test_linea_survey_policy_requires_lsst_dp1_group() -> None:
    policy = LineaSurveyAccessPolicy()
    user = UserFactory()

    assert policy.can_request_cutout(user=user, survey_id="lsst_dp1") is False

    group, _ = Group.objects.get_or_create(name="lsst_dp1")
    user.groups.add(group)

    assert policy.can_request_cutout(user=user, survey_id="lsst_dp1") is True


def test_linea_survey_policy_requires_lsst_dp02_group() -> None:
    policy = LineaSurveyAccessPolicy()
    user = UserFactory()
    group, _ = Group.objects.get_or_create(name="lsst_dp0.2")
    user.groups.add(group)

    assert policy.can_request_cutout(user=user, survey_id="lsst_dp02") is True
    assert policy.can_request_cutout(user=user, survey_id="lsst_dp0.2") is True
    assert policy.can_request_cutout(user=user, survey_id="lsst_dp1") is False
