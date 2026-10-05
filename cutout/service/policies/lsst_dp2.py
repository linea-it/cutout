from __future__ import annotations

from typing import Any

from cutout.service.surveys import LSST_DP2_GROUP, LSST_DP2_ID

from .base import SurveyAccessPolicy


class LsstDp2AccessPolicy(SurveyAccessPolicy):
    survey_ids = frozenset({LSST_DP2_ID})

    def can_request_cutout(
        self,
        *,
        user: Any | None,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        if survey_id not in self.survey_ids:
            return False
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return user.groups.filter(name=LSST_DP2_GROUP).exists()
