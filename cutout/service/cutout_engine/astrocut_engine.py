from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from astrocut import fits_cut
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from cutout import __version__
from reproject import reproject_interp

from cutout.service.stencils import Stencil

from .base import CutoutEngine
from .color_composer import compose_rgb


def _count_data_extensions(hdul: fits.HDUList) -> int:
    return sum(1 for h in hdul if getattr(h, "data", None) is not None)


def _mosaic_extensions(
    hdul: fits.HDUList,
    *,
    center: SkyCoord,
    cutout_size,
    input_files: list[str],
    output_path: Path,
) -> Path:
    """Reproject multi-extension output from ``fits_cut`` onto a common grid."""

    data_hdus = [(i, h) for i, h in enumerate(hdul) if getattr(h, "data", None) is not None]
    if len(data_hdus) <= 1:
        return output_path

    print(f"[astrocut] _mosaic_extensions: combining {len(data_hdus)} tiles")

    ref_header = data_hdus[0][1].header
    ref_wcs = WCS(ref_header)
    pixel_scale = abs(ref_wcs.proj_plane_pixel_scales()[0].to_value(u.deg))

    if hasattr(cutout_size, "unit"):
        size_x = size_y = cutout_size.to(u.deg).value
    else:
        size_x = cutout_size[0].to(u.deg).value
        size_y = cutout_size[1].to(u.deg).value

    nx = max(int(size_x / pixel_scale), 1)
    ny = max(int(size_y / pixel_scale), 1)

    out_wcs = WCS(naxis=2)
    out_wcs.wcs.ctype = [ref_wcs.wcs.ctype[0], ref_wcs.wcs.ctype[1]]
    out_wcs.wcs.crval = [center.ra.deg, center.dec.deg]
    out_wcs.wcs.crpix = [nx / 2.0, ny / 2.0]
    out_wcs.wcs.cd = [[-pixel_scale, 0.0], [0.0, pixel_scale]]
    out_wcs.wcs.radesys = "ICRS"
    out_wcs.wcs.equinox = 2000.0

    arrays = []
    for _idx, hdu in data_hdus:
        arr, _ = reproject_interp(hdu, out_wcs, shape_out=(ny, nx), order="bilinear")
        arrays.append(arr.astype(np.float32))

    stack = np.stack(arrays)
    result = np.nanmean(stack, axis=0).astype(np.float32)
    result[np.all(np.isnan(stack), axis=0)] = np.nan

    out_header = out_wcs.to_header()
    out_header["HISTORY"] = f"Mosaic assembled from {len(data_hdus)} tiles using reproject_interp + nanmean"
    out_header["NINPUTS"] = (len(data_hdus), "Number of input tiles combined")
    out_header["METHOD"] = ("reproject_interp + nanmean", "Mosaicking method")
    out_header["IMGTYPE"] = ("mosaic", "Image type")
    for i, fpath in enumerate(input_files, 1):
        out_header[f"INFILE{i:02d}"] = (str(Path(fpath).name), f"Input tile {i}")
    out_header["ORIGIN"] = "data.linea.org.br"
    out_header["SOFTNAME"] = "LIneA Cutout Service"
    out_header["SOFTVERS"] = __version__

    for kw in ("BUNIT", "MAGZERO", "FILTER", "BAND", "RADESYS", "EQUINOX",
               "TELESCOP", "INSTRUME"):
        if kw in ref_header:
            out_header[kw] = ref_header[kw]

    primary = fits.PrimaryHDU(data=result, header=out_header)
    primary.writeto(output_path, overwrite=True)
    return output_path


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
        if output_format not in ("fits", "png"):
            raise ValueError("Astrocut engine currently supports only fits and png output")

        if not input_files:
            raise ValueError("Astrocut engine requires at least one input file")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_tag = uuid4().hex[:8]

        stencil_obj = Stencil.from_dict(stencil)
        coordinate = stencil_obj.get_center()
        cutout_size = stencil_obj.get_cutout_size()
        stencil_type = stencil.get("type", "circle")

        print(f"[astrocut] run_cutout: source_id={source_id} band={band} output_format={output_format} color={color} rgb_bands={rgb_bands} persist={persist}")
        print(f"[astrocut] run_cutout: stencil type={stencil_type} coordinate={coordinate} cutout_size={cutout_size}")
        print(f"[astrocut] run_cutout: input_files={input_files}")

        # --- FITS ---
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

            temp = fits.open(output_path)
            multi_tile = _count_data_extensions(temp) > 1
            temp.close()

            if multi_tile:
                _mosaic_extensions(
                    fits.open(output_path),
                    center=coordinate,
                    cutout_size=cutout_size,
                    input_files=list(input_files),
                    output_path=output_path,
                )
            else:
                with fits.open(output_path, mode="update") as hdul:
                    hdul[0].header["ORIGIN"] = "data.linea.org.br"
                    hdul[0].header["SOFTNAME"] = "LIneA Cutout Service"
                    hdul[0].header["SOFTVERS"] = __version__
                    hdul[0].header["HISTORY"] = "Cutout produced by LIneA Cutout Service"
            return output_path

        # --- PNG ---
        from PIL import Image, PngImagePlugin

        if output_format == "png" and color:
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
                res_path = Path(res)
                mosa = fits.open(res_path)
                if _count_data_extensions(mosa) > 1:
                    mosa.close()
                    _mosaic_extensions(
                        fits.open(res_path),
                        center=coordinate,
                        cutout_size=cutout_size,
                        input_files=list(files_b),
                        output_path=res_path,
                    )
                else:
                    mosa.close()
                print(f"[astrocut] fits_cut for band {b} produced {res_path}")
                temp_paths.append(res_path)

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

            min_rows = min(a.shape[0] for a in arrays)
            min_cols = min(a.shape[1] for a in arrays)
            arrays = [a[:min_rows, :min_cols] for a in arrays]

            rgb = compose_rgb(arrays, bands, source_id)

            # --- Embed WCS (from first band) + provenance into PNG for ds9 ---
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("ORIGIN", "data.linea.org.br")
            pnginfo.add_text("SOFTNAME", "LIneA Cutout Service")
            pnginfo.add_text("SOFTVERS", __version__)
            pnginfo.add_text("HISTORY", "RGB PNG composed from FITS cutouts using arcsinh stretch")

            with fits.open(temp_paths[0]) as wcs_hdul:
                wcs_header = wcs_hdul[0].header
                for h in wcs_hdul:
                    if getattr(h, "data", None) is not None:
                        wcs_header = h.header
                        break
            for kw in ("CTYPE1", "CTYPE2", "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2",
                       "CD1_1", "CD1_2", "CD2_1", "CD2_2", "NAXIS1", "NAXIS2",
                       "RADESYS", "EQUINOX"):
                if kw in wcs_header:
                    pnginfo.add_text(kw, str(wcs_header[kw]))

            img = Image.fromarray(rgb)
            img.save(output_path, pnginfo=pnginfo, compress_level=9, optimize=True)
            print(f"[astrocut] saved PNG at {output_path} size={output_path.stat().st_size}")

            for p in temp_paths:
                try:
                    p.unlink()
                except Exception:
                    pass
            return output_path

        # --- Mono PNG ---
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

        temp = fits.open(result_path)
        if _count_data_extensions(temp) > 1:
            temp.close()
            _mosaic_extensions(
                fits.open(result_path),
                center=coordinate,
                cutout_size=cutout_size,
                input_files=list(input_files) if isinstance(input_files, list) else [],
                output_path=result_path,
            )
        else:
            temp.close()

        print(f"[astrocut] mono fits_cut produced {result_path}")
        with fits.open(result_path) as hdul:
            # WCS lives in the data extension, not PRIMARY (HDU 0)
            wcs_header = hdul[0].header
            data_hdu = None
            for h in hdul:
                if getattr(h, "data", None) is not None:
                    wcs_header = h.header
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

        # --- Embed WCS + provenance into PNG for ds9 ---
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("ORIGIN", "data.linea.org.br")
        pnginfo.add_text("SOFTNAME", "LIneA Cutout Service")
        pnginfo.add_text("SOFTVERS", __version__)
        pnginfo.add_text("HISTORY", "Cutout produced by LIneA Cutout Service")
        for kw in ("CTYPE1", "CTYPE2", "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2",
                   "CD1_1", "CD1_2", "CD2_1", "CD2_2", "NAXIS1", "NAXIS2",
                   "RADESYS", "EQUINOX"):
            if kw in wcs_header:
                pnginfo.add_text(kw, str(wcs_header[kw]))

        img = Image.fromarray(arr)
        img.save(output_path, pnginfo=pnginfo, compress_level=9, optimize=True)
        try:
            result_path.unlink()
        except Exception:
            pass
        return output_path
