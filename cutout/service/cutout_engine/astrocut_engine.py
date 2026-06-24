from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from astrocut import fits_cut
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from reproject import reproject_interp

from cutout import __version__
from cutout.service.stencils import Stencil

from .base import CutoutEngine
from .color_composer import COLOR_PARAMS, _arcsinh_stretch, compose_rgb


def _mosaic_hdus(
    data_hdus: list,
    *,
    center: SkyCoord,
    cutout_size,
    input_files: list[str],
    ref_header: fits.Header,
) -> fits.PrimaryHDU:
    """Reproject data HDUs onto a common grid. Returns a single PrimaryHDU."""

    print(f"[astrocut] _mosaic_hdus: combining {len(data_hdus)} tiles")

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
        hdu.data = None  # free original cutout, no longer needed after reprojection

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

    for kw in ("BUNIT", "MAGZERO", "FILTER", "BAND", "RADESYS", "EQUINOX", "TELESCOP", "INSTRUME"):
        if kw in ref_header:
            out_header[kw] = ref_header[kw]

    return fits.PrimaryHDU(data=result, header=out_header)


def _extract_data_hdus(hdul: fits.HDUList) -> list[tuple[int, fits.HDU]]:
    """Return list of (index, hdu) for extensions that carry data."""
    return [(i, h) for i, h in enumerate(hdul) if getattr(h, "data", None) is not None]


def _add_provenance(header: fits.Header) -> None:
    header["ORIGIN"] = "data.linea.org.br"
    header["SOFTNAME"] = "LIneA Cutout Service"
    header["SOFTVERS"] = __version__
    header["HISTORY"] = "Cutout produced by LIneA Cutout Service"


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

        stencil_obj = Stencil.from_dict(stencil)
        coordinate = stencil_obj.get_center()
        cutout_size = stencil_obj.get_cutout_size()
        stencil_type = stencil.get("type", "circle")

        print(
            f"[astrocut] run_cutout: source_id={source_id} band={band} output_format={output_format} color={color} rgb_bands={rgb_bands} persist={persist}"
        )
        print(f"[astrocut] run_cutout: stencil type={stencil_type} coordinate={coordinate} cutout_size={cutout_size}")
        print(f"[astrocut] run_cutout: input_files={input_files}")

        # --- FITS ---
        if output_format == "fits":
            results = fits_cut(
                input_files=input_files,
                coordinates=coordinate,
                cutout_size=cutout_size,
                single_outfile=True,
                memory_only=True,
            )
            hdul = results[0]
            data_hdus = _extract_data_hdus(hdul)

            if len(data_hdus) > 1:
                ref_header = data_hdus[0][1].header
                primary = _mosaic_hdus(
                    data_hdus,
                    center=coordinate,
                    cutout_size=cutout_size,
                    input_files=list(input_files),
                    ref_header=ref_header,
                )
            else:
                hdu = data_hdus[0][1]
                primary = fits.PrimaryHDU(data=hdu.data, header=hdu.header)
                _add_provenance(primary.header)

            primary.writeto(output_path, overwrite=True)
            print(f"[astrocut] wrote FITS to {output_path}")
            return output_path

        # --- Color PNG ---
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

            arrays = []
            wcs_header = None
            for b in bands:
                files_b = input_files.get(b)
                if not files_b:
                    raise ValueError(f"No input files provided for band {b}")

                results = fits_cut(
                    input_files=files_b,
                    coordinates=coordinate,
                    cutout_size=cutout_size,
                    single_outfile=True,
                    memory_only=True,
                )
                hdul = results[0]
                data_hdus = _extract_data_hdus(hdul)

                if len(data_hdus) > 1:
                    ref_header = data_hdus[0][1].header
                    primary = _mosaic_hdus(
                        data_hdus,
                        center=coordinate,
                        cutout_size=cutout_size,
                        input_files=list(files_b),
                        ref_header=ref_header,
                    )
                    arr = primary.data
                    if wcs_header is None:
                        wcs_header = primary.header
                else:
                    hdu = data_hdus[0][1]
                    arr = hdu.data
                    if wcs_header is None:
                        wcs_header = hdu.header

                arr = np.nan_to_num(arr).astype(np.float32)
                print(f"[astrocut] band {b}: dtype={arr.dtype} shape={arr.shape} min={arr.min()} max={arr.max()}")
                arrays.append(arr)

            min_rows = min(a.shape[0] for a in arrays)
            min_cols = min(a.shape[1] for a in arrays)
            arrays = [a[:min_rows, :min_cols] for a in arrays]

            rgb = compose_rgb(arrays, bands, source_id)

            # --- Embed provenance + WCS into PNG ---
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("ORIGIN", "data.linea.org.br")
            pnginfo.add_text("SOFTNAME", "LIneA Cutout Service")
            pnginfo.add_text("SOFTVERS", __version__)
            pnginfo.add_text("HISTORY", "RGB PNG composed from FITS cutouts using arcsinh stretch")

            if wcs_header is not None:
                for kw in (
                    "CTYPE1",
                    "CTYPE2",
                    "CRPIX1",
                    "CRPIX2",
                    "CRVAL1",
                    "CRVAL2",
                    "CD1_1",
                    "CD1_2",
                    "CD2_1",
                    "CD2_2",
                    "CDELT1",
                    "CDELT2",
                    "PC1_1",
                    "PC1_2",
                    "PC2_1",
                    "PC2_2",
                    "NAXIS1",
                    "NAXIS2",
                    "RADESYS",
                    "EQUINOX",
                ):
                    if kw in wcs_header:
                        pnginfo.add_text(kw, str(wcs_header[kw]))

            img = Image.fromarray(rgb)
            img.save(output_path, pnginfo=pnginfo, compress_level=9, optimize=True)
            print(f"[astrocut] saved PNG at {output_path} size={output_path.stat().st_size}")
            return output_path

        # --- Mono PNG ---
        from PIL import Image, PngImagePlugin

        results = fits_cut(
            input_files=input_files if isinstance(input_files, list) else [],
            coordinates=coordinate,
            cutout_size=cutout_size,
            single_outfile=True,
            memory_only=True,
        )
        hdul = results[0]
        data_hdus = _extract_data_hdus(hdul)

        if len(data_hdus) > 1:
            ref_header = data_hdus[0][1].header
            primary = _mosaic_hdus(
                data_hdus,
                center=coordinate,
                cutout_size=cutout_size,
                input_files=list(input_files) if isinstance(input_files, list) else [],
                ref_header=ref_header,
            )
            data = primary.data
            wcs_header = primary.header
        else:
            hdu = data_hdus[0][1]
            data = hdu.data
            wcs_header = hdu.header

        arr = np.nan_to_num(data).astype(np.float32)
        cfg = COLOR_PARAMS.get(source_id, {}).get("arcsinh_clip", {})
        if band in cfg:
            arr = _arcsinh_stretch(arr, *cfg[band])
        else:
            arr -= arr.min()
            if arr.max() > 0:
                arr = (arr / arr.max() * 255.0).astype("uint8")
            else:
                arr = arr.astype("uint8")

        # --- Embed provenance + WCS into PNG ---
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("ORIGIN", "data.linea.org.br")
        pnginfo.add_text("SOFTNAME", "LIneA Cutout Service")
        pnginfo.add_text("SOFTVERS", __version__)
        pnginfo.add_text("HISTORY", "Cutout produced by LIneA Cutout Service")
        for kw in (
            "CTYPE1",
            "CTYPE2",
            "CRPIX1",
            "CRPIX2",
            "CRVAL1",
            "CRVAL2",
            "CD1_1",
            "CD1_2",
            "CD2_1",
            "CD2_2",
            "CDELT1",
            "CDELT2",
            "PC1_1",
            "PC1_2",
            "PC2_1",
            "PC2_2",
            "NAXIS1",
            "NAXIS2",
            "RADESYS",
            "EQUINOX",
        ):
            if kw in wcs_header:
                pnginfo.add_text(kw, str(wcs_header[kw]))

        img = Image.fromarray(arr)
        img.save(output_path, pnginfo=pnginfo, compress_level=9, optimize=True)
        print(f"[astrocut] saved PNG at {output_path} size={output_path.stat().st_size}")
        return output_path
