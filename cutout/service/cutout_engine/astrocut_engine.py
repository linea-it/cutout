from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import CutoutEngine


class AstrocutEngine(CutoutEngine):
    def run_cutout(
        self,
        *,
        source_id: str,
        stencil: dict[str, Any],
        band: str,
        output_format: str,
        output_path: str | Path,
    ) -> Path:
        raise NotImplementedError("AstrocutEngine will be implemented in a future phase")
