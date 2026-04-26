from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class CutoutEngine(ABC):
    @abstractmethod
    def run_cutout(
        self,
        *,
        source_id: str,
        stencil: dict[str, Any],
        band: str,
        output_format: str,
        output_path: str | Path,
    ) -> Path:
        """Run a cutout request and return the generated file path."""
