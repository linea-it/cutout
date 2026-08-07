"""Exceptions for the image cutout service."""

from __future__ import annotations

from cutout.service.uws.exceptions import ParameterError

__all__ = ["InvalidCutoutParameterError"]


class InvalidCutoutParameterError(ParameterError):
    """The parameters for the cutout were invalid."""
