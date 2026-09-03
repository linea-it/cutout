from __future__ import annotations

from .base import FileLocator
from .des_dr2 import DesDr2FileLocator
from .lsst_dp1 import LsstDp1FileLocator

_LOCATOR_CLASSES: tuple[type[FileLocator], ...] = (
    DesDr2FileLocator,
    LsstDp1FileLocator,
)


def get_file_locator(survey_id: str, **kwargs) -> FileLocator:
    for cls in _LOCATOR_CLASSES:
        if survey_id in cls.survey_ids:
            return cls(**kwargs)
    raise ValueError(f"Unsupported survey_id: {survey_id}")
