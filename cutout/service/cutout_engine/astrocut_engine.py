from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

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
        input_files: list[str] | dict[str, list[str]] | None,
        band: str,
        output_format: str,
        output_path: str | Path,
        color: bool = False,
        rgb_bands: str | None = None,
        persist: bool = False,
    ) -> Path:
        # Accept png output (mono and rgb) in addition to fits.
        if output_format not in ("fits", "png"):
            raise ValueError("Astrocut engine currently supports only fits and png output")

        if not input_files:
            raise ValueError("Astrocut engine requires at least one input file")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_tag = uuid4().hex[:8]

        stencil_type = stencil.get("type", "circle")
        if stencil_type == "circle":
            center = stencil["center"]
            coordinate = SkyCoord(ra=center["ra"] * u.deg, dec=center["dec"] * u.deg, frame="icrs")
            cutout_size = 2 * stencil["radius"] * u.arcmin
        elif stencil_type == "range":
            ra_min, ra_max = stencil["ra"]
            dec_min, dec_max = stencil["dec"]
            coordinate = SkyCoord(
                ra=(ra_min + ra_max) / 2 * u.deg,
                dec=(dec_min + dec_max) / 2 * u.deg,
                frame="icrs",
            )
            cutout_size = [(ra_max - ra_min) * u.deg, (dec_max - dec_min) * u.deg]
        elif stencil_type == "polygon":
            vertices = stencil["vertices"]
            ras = [v[0] for v in vertices]
            decs = [v[1] for v in vertices]
            ra_min, ra_max = min(ras), max(ras)
            dec_min, dec_max = min(decs), max(decs)
            coordinate = SkyCoord(
                ra=(ra_min + ra_max) / 2 * u.deg,
                dec=(dec_min + dec_max) / 2 * u.deg,
                frame="icrs",
            )
            cutout_size = [(ra_max - ra_min) * u.deg, (dec_max - dec_min) * u.deg]
        else:
            raise ValueError(f"Unknown stencil type: {stencil_type}")

        # Debug info: log input files and parameters
        print(f"[astrocut] run_cutout: source_id={source_id} band={band} output_format={output_format} color={color} rgb_bands={rgb_bands} persist={persist}")
        print(f"[astrocut] run_cutout: stencil type={stencil_type} coordinate={coordinate} cutout_size={cutout_size}")
        print(f"[astrocut] run_cutout: input_files={input_files}")

        # For FITS, reuse fits_cut
        if output_format == "fits":
            result = fits_cut(
                input_files=input_files,
                coordinates=coordinate,
                cutout_size=cutout_size,
                single_outfile=True,
                cutout_prefix=output_path.stem,
                output_dir=output_path.parent,
            )

            print(f"[astrocut] fits_cut produced {result}")

            result_path = Path(result)
            if result_path != output_path:
                shutil.move(str(result_path), str(output_path))

            return output_path

        # For PNG, support mono and RGB composition
        from astropy.io import fits
        import numpy as np
        from PIL import Image

        if output_format == "png" and color:
            # Expect input_files as a dict: band -> list[str]
            if not isinstance(input_files, dict):
                raise ValueError("Color PNG requires input_files as a mapping band->files")

            raw = rgb_bands or "gri"
            if "," in raw:
                bands = [b.strip() for b in raw.split(",") if b.strip()]
            elif " " in raw:
                bands = [b.strip() for b in raw.split() if b.strip()]
            else:
                bands = list(raw)

            temp_paths = []
            arrays = []
            for b in bands:
                files_b = input_files.get(b)
                if not files_b:
                    raise ValueError(f"No input files provided for band {b}")

                temp_fits = output_path.with_name(f"{output_path.stem}_{temp_tag}_{b}.fits")
                print(f"[astrocut] creating temp fits for band {b} at {temp_fits} using files {files_b}")
                res = fits_cut(
                    input_files=files_b,
                    coordinates=coordinate,
                    cutout_size=cutout_size,
                    single_outfile=True,
                    cutout_prefix=temp_fits.stem,
                    output_dir=temp_fits.parent,
                )
                print(f"[astrocut] fits_cut for band {b} produced {res}")
                temp_paths.append(Path(res))

            # Read arrays: find first HDU with data in each FITS (astrocut writes CUTOUT extension)
            for p in temp_paths:
                with fits.open(p) as hdul:
                    data_hdu = None
                    for h in hdul:
                        if getattr(h, "data", None) is not None:
                            data_hdu = h.data
                            break
                    if data_hdu is None:
                        raise ValueError(f"No data HDU found in {p}")
                    arr = np.nan_to_num(data_hdu).astype(float)
                    print(f"[astrocut] read array from {p}: dtype={arr.dtype} shape={arr.shape} min={arr.min()} max={arr.max()}")
                    arrays.append(arr)

            # Ensure same shape by cropping to minimal shape
            min_rows = min(a.shape[0] for a in arrays)
            min_cols = min(a.shape[1] for a in arrays)
            chans = []
            for a in arrays:
                a_crop = a[:min_rows, :min_cols]
                a_crop -= a_crop.min()
                if a_crop.max() > 0:
                    a_crop = (a_crop / a_crop.max() * 255.0).astype('uint8')
                else:
                    a_crop = a_crop.astype('uint8')
                chans.append(a_crop)

            # Stack channels into RGB (order: channels[0]->R, [1]->G, [2]->B)
            rgb = np.dstack(chans[:3]) if len(chans) >= 3 else np.dstack([chans[0]] * 3)
            print(f"[astrocut] composing RGB image shape={rgb.shape} dtype={rgb.dtype}")
            img = Image.fromarray(rgb, mode="RGB")
            img.save(output_path)
            print(f"[astrocut] saved PNG at {output_path} size={output_path.stat().st_size}")

            # Cleanup temps
            for p in temp_paths:
                try:
                    p.unlink()
                except Exception:
                    pass

            return output_path

        # Fallback: single-band mono PNG conversion
        temp_fits = output_path.with_name(f"{output_path.stem}_{temp_tag}_mono.fits")
        result = fits_cut(
            input_files=input_files if isinstance(input_files, list) else ([] if input_files is None else []),
            coordinates=coordinate,
            cutout_size=cutout_size,
            single_outfile=True,
            cutout_prefix=temp_fits.stem,
            output_dir=temp_fits.parent,
        )

        result_path = Path(result)

        print(f"[astrocut] mono fits_cut produced {result_path}")
        with fits.open(result_path) as hdul:
            data_hdu = None
            for h in hdul:
                if getattr(h, "data", None) is not None:
                    data_hdu = h.data
                    break
            if data_hdu is None:
                raise ValueError(f"No data HDU found in {result_path}")
            data = data_hdu

        arr = np.nan_to_num(data).astype(float)
        arr -= arr.min()
        if arr.max() > 0:
            arr = (arr / arr.max() * 255.0).astype('uint8')
        else:
            arr = arr.astype('uint8')

        img = Image.fromarray(arr)
        img.save(output_path)

        try:
            result_path.unlink()
        except Exception:
            pass

        return output_path
