from __future__ import annotations

from .astrocut_engine import AstrocutEngine
from .base import CutoutEngine
from .des_engine import DesCutoutEngine


def create_cutout_engine(engine_name: str) -> CutoutEngine:
    name = engine_name.lower()

    if name == "astrocut":
        return AstrocutEngine()
    if name in ("legacy", "des"):
        return DesCutoutEngine()

    raise ValueError(f"Unsupported cutout engine: {engine_name}")
