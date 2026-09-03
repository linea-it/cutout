from __future__ import annotations

from typing import Any

from .base import SurveyAccessPolicy
from .des_dr2 import DesDr2AccessPolicy
from .lsst_dp1 import LsstDp1AccessPolicy

_POLICIES: tuple[SurveyAccessPolicy, ...] = (
    DesDr2AccessPolicy(),
    LsstDp1AccessPolicy(),
)


def get_survey_access_policy(survey_id: str) -> SurveyAccessPolicy | None:
    for policy in _POLICIES:
        if policy.handles(survey_id):
            return policy
    return None


def can_request_cutout(
    *,
    user: Any | None,
    survey_id: str,
    release: str | None = None,
) -> bool:
    policy = get_survey_access_policy(survey_id)
    if policy is None:
        return False
    return policy.can_request_cutout(user=user, survey_id=survey_id, release=release)
