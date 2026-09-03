from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class SurveyAccessPolicy(ABC):
    survey_ids: ClassVar[frozenset[str]]

    def handles(self, survey_id: str) -> bool:
        return survey_id in self.survey_ids

    @abstractmethod
    def can_request_cutout(
        self,
        *,
        user: Any | None,
        survey_id: str,
        release: str | None = None,
    ) -> bool:
        """Return whether the user can request cutouts from this survey."""
