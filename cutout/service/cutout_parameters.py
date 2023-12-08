"""Representation of request parameters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from cutout.service.exceptions import InvalidCutoutParameterError
from cutout.service.stencils import Stencil, parse_stencil
from cutout.service.uws.models import JobParameter


@dataclass
class CutoutParameters:
    """The parameters to a cutout request."""

    ids: list[str]
    """The dataset IDs on which to operate."""

    stencils: list[Stencil]
    """The cutout stencils to apply."""

    bands: list[str]

    formats: list[str]

    @classmethod
    def from_job_parameters(cls, params: list[JobParameter]) -> CutoutParameters:
        """Convert generic UWS parameters to the image cutout parameters.

        Parameters
        ----------
        params
            Generic input job parameters.

        Returns
        -------
        CutoutParameters
            The parsed cutout parameters specific to the image cutout service.

        Raises
        ------
        vocutouts.exceptions.InvalidCutoutParameterError
            One of the parameters could not be parsed.
        """
        ids = []
        formats = []
        bands = []
        stencils = []
        try:
            for param in params:
                if param.parameter_id == "id":
                    ids.append(param.value)
                elif param.parameter_id == "format":
                    formats.append(param.value)
                elif param.parameter_id == "band":
                    bands.append(param.value)
                else:
                    f = parse_stencil(param.parameter_id.upper(), param.value)
                    stencils.append(f)
        except Exception as e:
            msg = f"Invalid cutout parameter: {type(e).__name__}: {str(e)}"
            raise InvalidCutoutParameterError(msg, params) from e
        if not ids:
            raise InvalidCutoutParameterError("No dataset ID given", params)
        if not stencils:
            raise InvalidCutoutParameterError("No cutout stencil given", params)
        return cls(ids=ids, formats=formats, bands=bands, stencils=stencils)
