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

    engines: list[str]
    colors: list[str]

    rgb_bands: list[str]

    persists: list[str]

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
        engines = []
        colors = []
        rgb_bands = []
        persists = []
        stencils = []
        try:
            for param in params:
                if param.parameter_id == "id":
                    ids.append(param.value)
                elif param.parameter_id == "format":
                    formats.append(param.value)
                elif param.parameter_id == "band":
                    bands.append(param.value)
                elif param.parameter_id == "engine":
                    engines.append(param.value)
                elif param.parameter_id == "color":
                    colors.append(param.value)
                elif param.parameter_id == "rgb_bands":
                    rgb_bands.append(param.value)
                elif param.parameter_id == "persist":
                    persists.append(param.value)
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
        # Defaults
        if not formats:
            formats = ["fits"]
        if not bands:
            bands = ["g"]
        if not engines:
            engines = ["astrocut"]
        if not colors:
            colors = ["false"]
        if not rgb_bands:
            rgb_bands = ["gri"]
        if not persists:
            persists = ["false"]

        return cls(ids=ids, formats=formats, bands=bands, engines=engines, colors=colors, rgb_bands=rgb_bands, persists=persists, stencils=stencils)
