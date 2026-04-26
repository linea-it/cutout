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
        # Accept png output (mono and rgb) in addition to fits.
        if output_format not in ("fits", "png"):
            raise ValueError("Astrocut engine currently supports only fits and png output")

        if not input_files:
            raise ValueError("Astrocut engine requires at least one input file")

        if stencil.get("type") != "circle":
            raise ValueError("Astrocut engine currently supports only circle stencil")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        center = stencil["center"]
        radius_arcmin = stencil["radius"]
        coordinate = SkyCoord(ra=center["ra"] * u.deg, dec=center["dec"] * u.deg, frame="icrs")

        # For FITS, reuse fits_cut
        if output_format == "fits":
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

        # For PNG, perform a simple single-band conversion using astrocut.fits_cut
        # by requesting a single FITS outfile then converting to PNG.
        # This is a minimal implementation for mono PNG; RGB composition
        # will be implemented in subsequent iterations.
        temp_fits = output_path.with_suffix(".fits")
        result = fits_cut(
            input_files=input_files,
            coordinates=coordinate,
            cutout_size=radius_arcmin * u.arcmin,
            single_outfile=True,
            cutout_prefix=temp_fits.stem,
            output_dir=temp_fits.parent,
        )

        result_path = Path(result)
        # Convert FITS to PNG (simple stretch using astropy.io)
        from astropy.io import fits
        import numpy as np
        from PIL import Image

        with fits.open(result_path) as hdul:
            data = hdul[0].data

        # Normalize to 0-255
        arr = np.nan_to_num(data).astype(float)
        arr -= arr.min()
        if arr.max() > 0:
            arr = (arr / arr.max() * 255.0).astype('uint8')
        else:
            arr = arr.astype('uint8')

        img = Image.fromarray(arr)
        img.save(output_path)

        # Clean up temporary FITS
        try:
            result_path.unlink()
        except Exception:
            pass

        return output_path
