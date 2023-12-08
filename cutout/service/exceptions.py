"""Exceptions for the image cutout service."""

from __future__ import annotations

from cutout.service.uws.exceptions import ParameterError
from cutout.service.uws.models import JobParameter

__all__ = ["InvalidCutoutParameterError"]


class InvalidCutoutParameterError(ParameterError):
    """The parameters for the cutout were invalid."""
