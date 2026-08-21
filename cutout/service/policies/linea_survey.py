from __future__ import annotations

from typing import Any

from .base import SurveyAccessPolicy

# Same access map as sky-viewer (requireGroup / nginx_serve_protected_hips):
# public surveys have no group gate; private ones require CoManage groups.
PUBLIC_SURVEY_IDS = frozenset({"des_dr2"})

SURVEY_REQUIRED_GROUPS = {
    "lsst_dp02": "lsst_dp0.2",
    "lsst_dp0.2": "lsst_dp0.2",
    "lsst_dp1": "lsst_dp1",
}


class LineaSurveyAccessPolicy(SurveyAccessPolicy):
    def can_request_cutout(
        self,
        *,
        user: Any | None,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        if survey_id in PUBLIC_SURVEY_IDS:
            return True

        required_group = SURVEY_REQUIRED_GROUPS.get(survey_id)
        if required_group is None:
            return False

        if user is None or not getattr(user, "is_authenticated", False):
            return False

        return user.groups.filter(name=required_group).exists()
