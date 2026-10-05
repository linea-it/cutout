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

    def find_files_for_bands(
        self,
        *,
        survey_id: str,
        stencil: Stencil,
        bands: list[str],
    ) -> dict[str, list[FileDescriptor]]:
        """Return intersecting files for multiple bands.

        Locators with a resident spatial index should override this to run the
        geometric query once and derive each band's path from the same tiles.
        """
        return {band: self.find_files(survey_id=survey_id, stencil=stencil, band=band) for band in bands}

    def preload(self) -> None:
        """Load any resident discovery data before the process accepts work."""
