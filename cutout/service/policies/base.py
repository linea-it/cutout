from __future__ import annotations

from abc import ABC, abstractmethod


class SurveyAccessPolicy(ABC):
    @abstractmethod
    def can_request_cutout(
        self,
        *,
        user_id: str,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        """Return whether the user can request cutouts from this survey."""
