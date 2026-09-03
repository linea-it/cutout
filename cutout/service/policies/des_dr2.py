from __future__ import annotations

from typing import Any

from cutout.service.surveys import DES_DR2_ID

from .base import SurveyAccessPolicy


class DesDr2AccessPolicy(SurveyAccessPolicy):
    """DES DR2 is public: any caller may request cutouts for this survey."""

    survey_ids = frozenset({DES_DR2_ID})

    def can_request_cutout(
        self,
        *,
        user: Any | None,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        # Intentional: no auth/group check for the public DES DR2 release.
        return survey_id in self.survey_ids
