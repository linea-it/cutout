from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SurveyAccessPolicy(ABC):
    @abstractmethod
    def can_request_cutout(
        self,
        *,
        user: Any | None,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        """Return whether the user can request cutouts from this survey."""
