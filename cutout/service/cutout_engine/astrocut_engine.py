from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import CutoutEngine
from .des_engine import DesCutoutEngine


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
        # Temporary fallback: keep astrocut API option functional using the current DES engine.
        return DesCutoutEngine().run_cutout(
            source_id=source_id,
            stencil=stencil,
            band=band,
            output_format=output_format,
            output_path=output_path,
        )
