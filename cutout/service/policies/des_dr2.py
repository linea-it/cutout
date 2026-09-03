from __future__ import annotations

from typing import Any

from cutout.service.surveys import DES_DR2_ID

from .base import SurveyAccessPolicy


class DesDr2AccessPolicy(SurveyAccessPolicy):
    survey_ids = frozenset({DES_DR2_ID})

    def can_request_cutout(
        self,
        *,
        user: Any | None,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        return survey_id in self.survey_ids
