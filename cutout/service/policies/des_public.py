from __future__ import annotations

from .base import SurveyAccessPolicy


class DesPublicAccessPolicy(SurveyAccessPolicy):
    def can_request_cutout(
        self,
        *,
        user_id: str,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        # DES DR2 is public in the current phase, so requests are always allowed.
        if survey_id == "des_dr2":
            return True

        return False
