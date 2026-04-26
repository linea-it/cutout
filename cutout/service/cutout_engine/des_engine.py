from __future__ import annotations

from pathlib import Path
from typing import Any

from cutout.lib.cutout import Cutout

from .base import CutoutEngine


class DesCutoutEngine(CutoutEngine):
    def run_cutout(
        self,
        *,
        source_id: str,
        stencil: dict[str, Any],
        input_files: list[str] | dict[str, list[str]] | None,
        band: str,
        output_format: str,
        output_path: str | Path,
        color: bool = False,
        rgb_bands: str | None = None,
        persist: bool = False,
    ) -> Path:
        # Legacy engine: ignore `input_files` mapping (discovery is internal to DesCutout)
        cutout = Cutout(source_id=source_id, stencil=stencil, band=band, format=output_format)
        return cutout.create(output_path)
