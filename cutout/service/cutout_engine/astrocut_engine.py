from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
from cutout.service.cutout_engine.resources import ExecutionPlan, plan_band_execution
from cutout.service.stencils import Stencil

from .base import CutoutEngine
from .color_composer import COLOR_PARAMS, _arcsinh_stretch, compose_rgb

logger = logging.getLogger("cutout")

# Workaround: astrocut.fits_cut._get_img_wcs mutates process-global
# astropy_log.handlers without a lock, causing "dictionary changed size
# during iteration" when two threads call fits_cut concurrently.
_fits_cut_lock = threading.Lock()

_WCS_PNG_KEYS = (
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
)


def _setting(name: str, default: int) -> int:
    try:
        from django.conf import settings

        if not settings.configured:
            return default
        return int(getattr(settings, name, default))
    except Exception:
        return default


def _cutout_extents_deg(cutout_size) -> tuple[float, float]:
    if hasattr(cutout_size, "unit"):
        value = float(cutout_size.to(u.deg).value)
        return value, value
    return float(cutout_size[0].to(u.deg).value), float(cutout_size[1].to(u.deg).value)


def output_grid(
    center: SkyCoord,
    cutout_size,
    pixel_scale: float,
    max_dim: int | None = None,
) -> tuple[WCS, int, int, float]:
    """Build an ICRS TAN-like grid. PNG may downsample; FITS keeps native scale."""
    size_x, size_y = _cutout_extents_deg(cutout_size)
    scale = float(pixel_scale)
    nx = max(int(size_x / scale), 1)
    ny = max(int(size_y / scale), 1)
    if max_dim and max_dim > 0:
        longest = max(nx, ny)
        if longest > max_dim:
            scale = scale * (longest / max_dim)
            nx = max(int(size_x / scale), 1)
            ny = max(int(size_y / scale), 1)
            nx = min(nx, max_dim)
            ny = min(ny, max_dim)

    out_wcs = WCS(naxis=2)
    out_wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    out_wcs.wcs.crval = [center.ra.deg, center.dec.deg]
    out_wcs.wcs.crpix = [nx / 2.0, ny / 2.0]
    out_wcs.wcs.cd = [[-scale, 0.0], [0.0, scale]]
    out_wcs.wcs.radesys = "ICRS"
    out_wcs.wcs.equinox = 2000.0
    return out_wcs, ny, nx, scale


def _pixel_scale_deg(header: fits.Header) -> float | None:
    try:
        wcs = WCS(header)
        if not wcs.has_celestial:
            return None
        return float(abs(wcs.proj_plane_pixel_scales()[0].to_value(u.deg)))
    except Exception:
        return None


def _has_celestial_wcs(header: fits.Header) -> bool:
    try:
        return bool(WCS(header).has_celestial)
    except Exception:
        return False


_SKIP_EXTNAMES = frozenset({"MSK", "MASK", "WGT", "WEIGHT", "VAR", "DQ", "UNCERT", "INVVAR"})


def _extract_data_hdus(hdul: fits.HDUList) -> list[tuple[int, fits.HDU]]:
    return [(i, h) for i, h in enumerate(hdul) if getattr(h, "data", None) is not None]


def _extract_science_hdus(hdul: fits.HDUList) -> list[tuple[int, fits.HDU]]:
    """Select the science HDU from headers without decoding image data."""
    kept: list[tuple[int, fits.HDU]] = []
    for i, hdu in enumerate(hdul):
        header = hdu.header
        if int(header.get("NAXIS", 0)) < 2:
            continue
        if int(header.get("NAXIS1", 0)) <= 0 or int(header.get("NAXIS2", 0)) <= 0:
            continue
        name = str(hdu.header.get("EXTNAME", "")).upper()
        if name in _SKIP_EXTNAMES:
            continue
        kept.append((i, hdu))
    preferred = [item for item in kept if str(item[1].header.get("EXTNAME", "")).upper() in {"SCI", "IMAGE"}]
    if preferred:
        return preferred[:1]
    return kept[:1] if kept else []


def _add_provenance(header: fits.Header) -> None:
    header["ORIGIN"] = "data.linea.org.br"
    header["SOFTNAME"] = "LIneA Cutout Service"
    header["SOFTVERS"] = __version__
    header["HISTORY"] = "Cutout produced by LIneA Cutout Service"


def _sample_box_perimeter(
    width: int,
    height: int,
    samples_per_edge: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample an image perimeter every ~256 px to retain curved WCS edges."""
    if samples_per_edge is None:
        samples_per_edge = max(17, min(129, int(np.ceil(max(width, height) / 256)) + 1))
    xs = np.linspace(-0.5, width - 0.5, samples_per_edge, dtype=float)
    ys = np.linspace(-0.5, height - 0.5, samples_per_edge, dtype=float)
    perimeter_x = np.concatenate(
        [
            xs,
            xs,
            np.full(samples_per_edge, -0.5),
            np.full(samples_per_edge, width - 0.5),
        ]
    )
    perimeter_y = np.concatenate(
        [
            np.full(samples_per_edge, -0.5),
            np.full(samples_per_edge, height - 0.5),
            ys,
            ys,
        ]
    )
    return perimeter_x, perimeter_y


def _input_pixel_window(
    in_wcs: WCS,
    data_shape: tuple[int, int],
    out_wcs: WCS,
    ny: int,
    nx: int,
    margin: int = 8,
) -> tuple[int, int, int, int] | None:
    """Native-pixel bbox of the output sky on an input tile (numpy y, x)."""
    height, width = data_shape
    perimeter_x, perimeter_y = _sample_box_perimeter(nx, ny)
    world = out_wcs.pixel_to_world(perimeter_x, perimeter_y)
    ix, iy = in_wcs.world_to_pixel(world)
    if not np.any(np.isfinite(ix)) or not np.any(np.isfinite(iy)):
        return 0, height, 0, width
    x0 = max(int(np.floor(np.nanmin(ix))) - margin, 0)
    x1 = min(int(np.ceil(np.nanmax(ix))) + margin, width)
    y0 = max(int(np.floor(np.nanmin(iy))) - margin, 0)
    y1 = min(int(np.ceil(np.nanmax(iy))) + margin, height)
    if x1 <= x0 or y1 <= y0:
        return None
    return y0, y1, x0, x1


def _bin_factor(native_scale: float, out_scale: float) -> int:
    if native_scale <= 0 or out_scale <= 0:
        return 1
    return max(int(out_scale / native_scale), 1)


def _mean_binned_section(
    data_ref,
    bbox: tuple[int, int, int, int],
    factor: int,
    *,
    output_chunk_rows: int = 128,
) -> np.ndarray:
    """Read and mean-bin a FITS section in bounded native-resolution chunks."""
    y0, y1, x0, x1 = bbox
    if factor <= 1:
        return np.asarray(data_ref[y0:y1, x0:x1], dtype=np.float32)

    trim_y = ((y1 - y0) // factor) * factor
    trim_x = ((x1 - x0) // factor) * factor
    if trim_y == 0 or trim_x == 0:
        return np.asarray(data_ref[y0:y1, x0:x1], dtype=np.float32)

    out_rows = trim_y // factor
    out_cols = trim_x // factor
    x_end = x0 + trim_x
    result = np.full((out_rows, out_cols), np.nan, dtype=np.float32)
    for out_y0 in range(0, out_rows, output_chunk_rows):
        out_y1 = min(out_y0 + output_chunk_rows, out_rows)
        src_y0 = y0 + out_y0 * factor
        src_y1 = y0 + out_y1 * factor
        chunk = np.asarray(data_ref[src_y0:src_y1, x0:x_end], dtype=np.float32)
        blocks = chunk.reshape(out_y1 - out_y0, factor, out_cols, factor)
        finite = np.isfinite(blocks)
        sums = np.nansum(blocks, axis=(1, 3), dtype=np.float64)
        counts = finite.sum(axis=(1, 3))
        np.divide(
            sums,
            counts,
            out=result[out_y0:out_y1],
            where=counts > 0,
            casting="unsafe",
        )
    return result


def _preview_section_hdu(hdu: fits.HDU, out_wcs: WCS, ny: int, nx: int, out_scale: float) -> fits.PrimaryHDU | None:
    """Slice the tile to the output sky and integer-bin to preview scale (no native fits_cut)."""
    in_wcs = WCS(hdu.header)
    height = int(hdu.header["NAXIS2"])
    width = int(hdu.header["NAXIS1"])
    bbox = _input_pixel_window(in_wcs, (height, width), out_wcs, ny, nx)
    if bbox is None:
        return None
    y0, y1, x0, x1 = bbox
    data_ref = hdu.section if hasattr(hdu, "section") else hdu.data
    sliced_wcs = in_wcs[y0:y1, x0:x1]
    native_scale = _pixel_scale_deg(hdu.header)
    factor = _bin_factor(native_scale or out_scale, out_scale)
    section = _mean_binned_section(data_ref, bbox, factor)
    if factor > 1 and section.shape[0] == (y1 - y0) // factor:
        trim_y = section.shape[0] * factor
        trim_x = section.shape[1] * factor
        sliced_wcs = sliced_wcs[:trim_y:factor, :trim_x:factor]
        logger.info(
            "[astrocut] preview bin factor=%s native_window=(%s,%s,%s,%s) binned=%s",
            factor,
            y0,
            y1,
            x0,
            x1,
            section.shape,
        )
    preview = fits.PrimaryHDU(data=section)
    preview.header.update(sliced_wcs.to_header())
    return preview


def _output_window(hdu: fits.HDU, out_wcs: WCS, ny: int, nx: int, margin: int = 4) -> tuple[int, int, int, int] | None:
    in_wcs = WCS(hdu.header)
    data = np.asarray(hdu.data)
    height, width = data.shape[-2], data.shape[-1]
    perimeter_x, perimeter_y = _sample_box_perimeter(width, height)
    world = in_wcs.pixel_to_world(perimeter_x, perimeter_y)
    ox, oy = out_wcs.world_to_pixel(world)
    if not np.any(np.isfinite(ox)) or not np.any(np.isfinite(oy)):
        return 0, ny, 0, nx
    x0 = max(int(np.floor(np.nanmin(ox))) - margin, 0)
    x1 = min(int(np.ceil(np.nanmax(ox))) + margin, nx)
    y0 = max(int(np.floor(np.nanmin(oy))) - margin, 0)
    y1 = min(int(np.ceil(np.nanmax(oy))) + margin, ny)
    if x1 <= x0 or y1 <= y0:
        return None
    return y0, y1, x0, x1


def _mosaic_header(out_wcs: WCS, ref_header: fits.Header, input_files: list[str], n_inputs: int) -> fits.Header:
    header = out_wcs.to_header()
    header["NAXIS"] = 2
    header["NAXIS1"] = int(out_wcs.pixel_shape[0]) if out_wcs.pixel_shape else header.get("NAXIS1", 0)
    header["NAXIS2"] = int(out_wcs.pixel_shape[1]) if out_wcs.pixel_shape else header.get("NAXIS2", 0)
    header["HISTORY"] = "Mosaic assembled from tiles using reproject_interp + nanmean"
    header["NINPUTS"] = (n_inputs, "Number of input tiles combined")
    header["METHOD"] = ("reproject_interp + nanmean", "Mosaicking method")
    header["IMGTYPE"] = ("mosaic", "Image type")
    for i, fpath in enumerate(input_files, 1):
        header[f"INFILE{i:02d}"] = (str(Path(fpath).name), f"Input tile {i}")
    _add_provenance(header)
    for kw in ("BUNIT", "MAGZERO", "FILTER", "BAND", "RADESYS", "EQUINOX", "TELESCOP", "INSTRUME"):
        if kw in ref_header:
            header[kw] = ref_header[kw]
    return header


def _downsample_array(arr: np.ndarray, max_dim: int | None) -> np.ndarray:
    if not max_dim or max_dim <= 0:
        return arr
    height, width = arr.shape[-2], arr.shape[-1]
    longest = max(height, width)
    if longest <= max_dim:
        return arr
    from PIL import Image

    scale = max_dim / longest
    new_w = max(int(round(width * scale)), 1)
    new_h = max(int(round(height * scale)), 1)
    img = Image.fromarray(np.nan_to_num(arr).astype(np.float32), mode="F")
    resized = np.array(img.resize((new_w, new_h), resample=Image.Resampling.BILINEAR), dtype=np.float32)
    return resized


def _reproject_kwargs(workers: int) -> dict[str, Any]:
    parallel: bool | int = False
    if workers > 1:
        parallel = int(workers)
    return {
        "order": "bilinear",
        "return_footprint": False,
        "block_size": "auto" if workers > 1 else None,
        "parallel": parallel,
    }


def _accumulate_hdu(
    hdu: fits.HDU,
    *,
    out_wcs: WCS,
    ny: int,
    nx: int,
    sum_arr: np.ndarray,
    count_arr: np.ndarray,
    workers: int,
) -> None:
    window = _output_window(hdu, out_wcs, ny, nx)
    if window is None:
        return
    y0, y1, x0, x1 = window
    window_wcs = out_wcs[y0:y1, x0:x1]
    shape = (y1 - y0, x1 - x0)
    t0 = time.perf_counter()
    arr = reproject_interp(
        hdu,
        window_wcs,
        shape_out=shape,
        output_array=np.full(shape, np.nan, dtype=np.float32),
        **_reproject_kwargs(workers),
    )
    if isinstance(arr, tuple):
        arr = arr[0]
    arr = np.asarray(arr, dtype=np.float32)
    valid = np.isfinite(arr)
    dest_sum = sum_arr[y0:y1, x0:x1]
    dest_count = count_arr[y0:y1, x0:x1]
    dest_sum[valid] += arr[valid]
    dest_count[valid] += 1
    logger.info(
        "[astrocut] reproject window=%s shape=%s workers=%s elapsed=%.3fs",
        window,
        shape,
        workers,
        time.perf_counter() - t0,
    )


def _fits_cut_one(*, input_files: list[str], coordinate: SkyCoord, cutout_size) -> fits.HDUList:
    with _fits_cut_lock:
        results = fits_cut(
            input_files=input_files,
            coordinates=coordinate,
            cutout_size=cutout_size,
            single_outfile=True,
            memory_only=True,
        )
    return results[0]


def _planning_grid(
    files: list[str],
    coordinate: SkyCoord,
    cutout_size,
    max_dim: int | None,
) -> tuple[int, int, int, int]:
    """Inspect one header and return target/native grid dimensions without data I/O."""
    _wcs, ny, nx, _scale = _output_grid_from_file(files, coordinate, cutout_size, max_dim)
    _native_wcs, native_ny, native_nx, _native_scale = _output_grid_from_file(
        files,
        coordinate,
        cutout_size,
        None,
    )
    return ny, nx, native_ny, native_nx


def _output_grid_from_file(
    files: list[str],
    coordinate: SkyCoord,
    cutout_size,
    max_dim: int | None,
) -> tuple[WCS, int, int, float]:
    """Build a target grid from the first science header without reading image data."""
    if not files:
        raise ValueError("Cannot plan cutout without input files")
    with fits.open(files[0], memmap=False) as hdul:
        science = _extract_science_hdus(hdul)
        if not science:
            raise ValueError(f"No science image HDU found in {files[0]}")
        scale = _pixel_scale_deg(science[0][1].header)
    if scale is None:
        raise ValueError(f"Science image in {files[0]} has no valid celestial WCS")
    return output_grid(coordinate, cutout_size, scale, max_dim=max_dim)


def _ensure_plan_fits_memory(plan: ExecutionPlan) -> None:
    if plan.estimated_band_bytes > plan.memory_budget_bytes:
        required_mb = plan.estimated_band_bytes // (1024 * 1024)
        budget_mb = plan.memory_budget_bytes // (1024 * 1024)
        raise MemoryError(
            f"Cutout requires approximately {required_mb} MiB per band; " f"configured task budget is {budget_mb} MiB"
        )


def process_band(
    *,
    files: list[str],
    coordinate: SkyCoord,
    cutout_size,
    max_dim: int | None,
    reproject_workers: int,
    band: str | None = None,
    native_cut: bool = True,
    target_grid: tuple[WCS, int, int, float] | None = None,
) -> tuple[np.ndarray, fits.Header]:
    """Mosaic one band onto a common grid. Inputs are serializable (paths).

    ``native_cut=True`` (FITS): ``fits_cut`` at survey resolution.
    ``native_cut=False`` (PNG): read each tile, bin to the preview scale, reproject
    onto the capped grid — never materializes a native-resolution cutout.
    """
    if not files:
        raise ValueError("process_band requires at least one input file")

    t_band = time.perf_counter()
    sum_arr: np.ndarray | None = None
    count_arr: np.ndarray | None = None
    out_wcs: WCS | None = None
    ref_header: fits.Header | None = None
    ny = nx = 0
    used_scale = 0.0
    n_used = 0

    for path in files:
        t_src = time.perf_counter()
        if native_cut:
            hdul = _fits_cut_one(input_files=[path], coordinate=coordinate, cutout_size=cutout_size)
            logger.info(
                "[astrocut] fits_cut band=%s file=%s elapsed=%.3fs",
                band,
                Path(path).name,
                time.perf_counter() - t_src,
            )
        else:
            hdul = fits.open(path, memmap=False)
            logger.info(
                "[astrocut] open_tile band=%s file=%s elapsed=%.3fs",
                band,
                Path(path).name,
                time.perf_counter() - t_src,
            )
        try:
            data_hdus = _extract_data_hdus(hdul) if native_cut else _extract_science_hdus(hdul)
            if not data_hdus:
                continue
            for _idx, hdu in data_hdus:
                header = hdu.header
                if ref_header is None:
                    ref_header = header
                scale = _pixel_scale_deg(header)
                if scale is None or not _has_celestial_wcs(header):
                    raise ValueError(f"Science image in {path} has no valid celestial WCS")
                if out_wcs is None:
                    if target_grid is None:
                        out_wcs, ny, nx, used_scale = output_grid(
                            coordinate,
                            cutout_size,
                            scale,
                            max_dim=max_dim,
                        )
                    else:
                        shared_wcs, ny, nx, used_scale = target_grid
                        out_wcs = shared_wcs.deepcopy()
                    out_wcs.pixel_shape = (nx, ny)
                    sum_arr = np.zeros((ny, nx), dtype=np.float32)
                    count_arr = np.zeros((ny, nx), dtype=np.uint16)
                    logger.info(
                        "[astrocut] band=%s grid=%sx%s scale=%.8g max_dim=%s tiles=%s native_cut=%s",
                        band,
                        ny,
                        nx,
                        used_scale,
                        max_dim,
                        len(files),
                        native_cut,
                    )
                assert sum_arr is not None and count_arr is not None and out_wcs is not None
                src_hdu = hdu
                if not native_cut:
                    preview = _preview_section_hdu(hdu, out_wcs, ny, nx, used_scale)
                    if preview is None:
                        continue
                    src_hdu = preview
                _accumulate_hdu(
                    src_hdu,
                    out_wcs=out_wcs,
                    ny=ny,
                    nx=nx,
                    sum_arr=sum_arr,
                    count_arr=count_arr,
                    workers=reproject_workers,
                )
                n_used += 1
                if native_cut:
                    hdu.data = None
        finally:
            close = getattr(hdul, "close", None)
            if callable(close):
                close()

    if sum_arr is None or count_arr is None or out_wcs is None or ref_header is None:
        raise ValueError("process_band produced no image data")

    with np.errstate(invalid="ignore", divide="ignore"):
        result = np.empty_like(sum_arr)
        valid = count_arr > 0
        result[valid] = sum_arr[valid] / count_arr[valid]
        result[~valid] = np.nan

    header = _mosaic_header(out_wcs, ref_header, files, n_used)
    header["NAXIS1"] = nx
    header["NAXIS2"] = ny
    if not native_cut:
        header["HISTORY"] = "PNG preview resampled from tiles; not a native-resolution cutout"
    logger.info(
        "[astrocut] band=%s mosaic done n_inputs=%s shape=%s elapsed=%.3fs",
        band,
        n_used,
        result.shape,
        time.perf_counter() - t_band,
    )
    return result, header


def _parse_rgb_bands(rgb_bands: str | None) -> list[str]:
    raw = rgb_bands or "gri"
    if "," in raw:
        return [b.strip() for b in raw.split(",") if b.strip()]
    if " " in raw:
        return [b.strip() for b in raw.split() if b.strip()]
    return list(raw)


def _save_png(path: Path, array: np.ndarray, header: fits.Header | None, history: str) -> None:
    from PIL import Image, PngImagePlugin

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("ORIGIN", "data.linea.org.br")
    pnginfo.add_text("SOFTNAME", "LIneA Cutout Service")
    pnginfo.add_text("SOFTVERS", __version__)
    pnginfo.add_text("HISTORY", history)
    if header is not None:
        for kw in _WCS_PNG_KEYS:
            if kw in header:
                pnginfo.add_text(kw, str(header[kw]))
    compress_level = max(0, min(_setting("CUTOUT_PNG_COMPRESS_LEVEL", 6), 9))
    t0 = time.perf_counter()
    img = Image.fromarray(array)
    img.save(path, pnginfo=pnginfo, compress_level=compress_level, optimize=False)
    logger.info("[astrocut] saved PNG %s size=%s elapsed=%.3fs", path, path.stat().st_size, time.perf_counter() - t0)


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
        png_max_dim = _setting("CUTOUT_PNG_MAX_DIM", 4096)
        png_max_dim = png_max_dim if png_max_dim > 0 else None

        logger.info(
            "[astrocut] run_cutout source_id=%s band=%s format=%s color=%s rgb_bands=%s persist=%s",
            source_id,
            band,
            output_format,
            color,
            rgb_bands,
            persist,
        )
        logger.info("[astrocut] stencil type=%s coordinate=%s cutout_size=%s", stencil_type, coordinate, cutout_size)

        if output_format == "fits":
            files = list(input_files) if isinstance(input_files, list) else []
            if len(files) <= 1:
                hdul = _fits_cut_one(input_files=files, coordinate=coordinate, cutout_size=cutout_size)
                data_hdus = _extract_data_hdus(hdul)
                hdu = data_hdus[0][1]
                primary = fits.PrimaryHDU(data=hdu.data, header=hdu.header)
                _add_provenance(primary.header)
            else:
                ny, nx, native_ny, native_nx = _planning_grid(files, coordinate, cutout_size, max_dim=None)
                plan = plan_band_execution(
                    n_bands=1,
                    ny=ny,
                    nx=nx,
                    native_ny=native_ny,
                    native_nx=native_nx,
                    n_tiles=len(files),
                    max_band_workers=1,
                )
                _ensure_plan_fits_memory(plan)
                arr, header = process_band(
                    files=files,
                    coordinate=coordinate,
                    cutout_size=cutout_size,
                    max_dim=None,
                    reproject_workers=plan.cpus,
                    band=band,
                    native_cut=True,
                )
                primary = fits.PrimaryHDU(data=arr, header=header)
            primary.writeto(output_path, overwrite=True)
            logger.info("[astrocut] wrote FITS to %s", output_path)
            return output_path

        if output_format == "png" and color:
            if not isinstance(input_files, dict):
                raise ValueError("Color PNG requires input_files as a mapping band->files")
            bands = _parse_rgb_bands(rgb_bands)
            n_tiles = max((len(input_files.get(b) or []) for b in bands), default=1)
            first_files = list(input_files.get(bands[0]) or [])
            ny, nx, native_ny, native_nx = _planning_grid(
                first_files,
                coordinate,
                cutout_size,
                max_dim=png_max_dim,
            )
            target_grid = _output_grid_from_file(
                first_files,
                coordinate,
                cutout_size,
                max_dim=png_max_dim,
            )
            plan = plan_band_execution(
                n_bands=len(bands),
                ny=ny,
                nx=nx,
                native_ny=native_ny,
                native_nx=native_nx,
                n_tiles=n_tiles,
            )
            _ensure_plan_fits_memory(plan)
            _run_color_png(
                source_id=source_id,
                input_files=input_files,
                bands=bands,
                coordinate=coordinate,
                cutout_size=cutout_size,
                output_path=output_path,
                max_dim=png_max_dim,
                plan=plan,
                target_grid=target_grid,
            )
            return output_path

        files = list(input_files) if isinstance(input_files, list) else []
        ny, nx, native_ny, native_nx = _planning_grid(files, coordinate, cutout_size, max_dim=png_max_dim)
        plan = plan_band_execution(
            n_bands=1,
            ny=ny,
            nx=nx,
            native_ny=native_ny,
            native_nx=native_nx,
            n_tiles=len(files),
        )
        _ensure_plan_fits_memory(plan)
        arr, header = process_band(
            files=files,
            coordinate=coordinate,
            cutout_size=cutout_size,
            max_dim=png_max_dim,
            reproject_workers=plan.cpus,
            band=band,
            native_cut=False,
        )
        arr = np.nan_to_num(arr).astype(np.float32)
        cfg = COLOR_PARAMS.get(source_id, {}).get("arcsinh_clip", {})
        if band in cfg:
            png_arr = _arcsinh_stretch(arr, *cfg[band])
        else:
            arr = arr - arr.min()
            if arr.max() > 0:
                png_arr = (arr / arr.max() * 255.0).astype("uint8")
            else:
                png_arr = arr.astype("uint8")
        _save_png(output_path, png_arr, header, "Cutout produced by LIneA Cutout Service")
        return output_path


def _run_color_png(
    *,
    source_id: str,
    input_files: dict[str, list[str]],
    bands: list[str],
    coordinate: SkyCoord,
    cutout_size,
    output_path: Path,
    max_dim: int | None,
    plan: ExecutionPlan,
    target_grid: tuple[WCS, int, int, float],
) -> None:
    t0 = time.perf_counter()
    indexed: list[tuple[int, str, list[str]]] = []
    for i, name in enumerate(bands):
        files_b = input_files.get(name)
        if not files_b:
            raise ValueError(f"No input files provided for band {name}")
        indexed.append((i, name, list(files_b)))

    results: list[tuple[np.ndarray, fits.Header] | None] = [None] * len(indexed)
    offset = 0
    while offset < len(indexed):
        end = offset + plan.concurrent_bands
        wave = indexed[offset:end]
        threads = plan.threads_for_wave(len(wave))
        logger.info("[astrocut] rgb wave=%s threads=%s", [name for _i, name, _f in wave], threads)

        def _one(item: tuple[int, str, list[str]], workers: int) -> tuple[int, np.ndarray, fits.Header]:
            idx, name, files_b = item
            arr, header = process_band(
                files=files_b,
                coordinate=coordinate,
                cutout_size=cutout_size,
                max_dim=max_dim,
                reproject_workers=workers,
                band=name,
                native_cut=False,
                target_grid=target_grid,
            )
            arr = np.nan_to_num(arr).astype(np.float32)
            logger.info(
                "[astrocut] band %s: dtype=%s shape=%s min=%s max=%s",
                name,
                arr.dtype,
                arr.shape,
                arr.min(),
                arr.max(),
            )
            return idx, arr, header

        if len(wave) == 1:
            idx, arr, header = _one(wave[0], threads[0])
            results[idx] = (arr, header)
        else:
            with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                futures = [pool.submit(_one, item, workers) for item, workers in zip(wave, threads, strict=True)]
                for fut in futures:
                    idx, arr, header = fut.result()
                    results[idx] = (arr, header)
        offset += len(wave)

    arrays = [item[0] for item in results if item is not None]
    wcs_header = results[0][1] if results[0] is not None else None
    shapes = {array.shape for array in arrays}
    if len(shapes) != 1:
        raise ValueError(f"RGB bands produced inconsistent output grids: {sorted(shapes)}")
    t_compose = time.perf_counter()
    rgb = compose_rgb(arrays, bands, source_id)
    logger.info("[astrocut] compose_rgb elapsed=%.3fs", time.perf_counter() - t_compose)
    _save_png(output_path, rgb, wcs_header, "RGB PNG composed from FITS cutouts using arcsinh stretch")
    logger.info("[astrocut] color png total elapsed=%.3fs", time.perf_counter() - t0)


def _mosaic_hdus(
    data_hdus: list,
    *,
    center: SkyCoord,
    cutout_size,
    input_files: list[str],
    ref_header: fits.Header,
    max_dim: int | None = None,
    max_workers: int = 1,
) -> fits.PrimaryHDU:
    """Reproject data HDUs onto a common grid. Kept for tests and FITS callers."""
    scale = _pixel_scale_deg(ref_header)
    if scale is None:
        raise ValueError("Cannot mosaic HDUs without a celestial WCS")
    out_wcs, ny, nx, _used = output_grid(center, cutout_size, scale, max_dim=max_dim)
    out_wcs.pixel_shape = (nx, ny)
    sum_arr = np.zeros((ny, nx), dtype=np.float32)
    count_arr = np.zeros((ny, nx), dtype=np.uint16)
    for _idx, hdu in data_hdus:
        _accumulate_hdu(
            hdu,
            out_wcs=out_wcs,
            ny=ny,
            nx=nx,
            sum_arr=sum_arr,
            count_arr=count_arr,
            workers=max_workers,
        )
        hdu.data = None
    with np.errstate(invalid="ignore", divide="ignore"):
        result = np.empty_like(sum_arr)
        valid = count_arr > 0
        result[valid] = sum_arr[valid] / count_arr[valid]
        result[~valid] = np.nan
    header = _mosaic_header(out_wcs, ref_header, input_files, len(data_hdus))
    header["NAXIS1"] = nx
    header["NAXIS2"] = ny
    return fits.PrimaryHDU(data=result, header=header)
