from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from astrocut import fits_cut
from astropy import units as u
from astropy.coordinates import SkyCoord

from .base import CutoutEngine


class AstrocutEngine(CutoutEngine):
    def run_cutout(
        self,
        *,
        source_id: str,
        stencil: dict[str, Any],
        input_files: list[str] | None,
        band: str,
        output_format: str,
        output_path: str | Path,
    ) -> Path:
        if output_format != "fits":
            raise ValueError("Astrocut engine currently supports only fits output")

        if not input_files:
            raise ValueError("Astrocut engine requires at least one input file")

        if stencil.get("type") != "circle":
            raise ValueError("Astrocut engine currently supports only circle stencil")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        center = stencil["center"]
        radius_arcmin = stencil["radius"]
        coordinate = SkyCoord(ra=center["ra"] * u.deg, dec=center["dec"] * u.deg, frame="icrs")

        result = fits_cut(
            input_files=input_files,
            coordinates=coordinate,
            cutout_size=radius_arcmin * u.arcmin,
            single_outfile=True,
            cutout_prefix=output_path.stem,
            output_dir=output_path.parent,
        )

        result_path = Path(result)
        if result_path != output_path:
            shutil.move(str(result_path), str(output_path))

        return output_path
