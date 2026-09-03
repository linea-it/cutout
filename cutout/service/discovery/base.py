from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from cutout.service.stencils import Stencil

from .models import FileDescriptor


class FileLocator(ABC):
    survey_ids: ClassVar[frozenset[str]]

    @abstractmethod
    def find_files(
        self,
        *,
        survey_id: str,
        stencil: Stencil,
        band: str | None = None,
    ) -> list[FileDescriptor]:
        """Return files that intersect the requested stencil."""
