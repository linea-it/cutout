#!/usr/bin/env python3
"""Debug script for cutout generation.

Creates FITS and PNG artefacts using legacy and DesCutout functions and
inspects the generated files (size, shape, min/max, nan counts).

Run inside container:

  docker compose exec django python scripts/debug_cutout.py

"""
from pathlib import Path
import sys
import traceback

from PIL import Image
import numpy as np
from astropy.io import fits

from cutout.lib.des_cutout import DesCutout
from cutout.lib.cutout import Cutout
from cutout.service.discovery.des_csv_locator import DesCsvFileLocator


OUT_DIR = Path("/data/results/debug")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_fits(path: Path):
    print(f"Inspecting FITS: {path}")
    if not path.exists():
        print("  MISSING")
        return
    print(f"  size_bytes: {path.stat().st_size}")
    try:
        with fits.open(path) as hdul:
            print("  HDU list:")
            hdul.info(output=sys.stdout)
            # try to find first HDU with data
            found = False
            for i, h in enumerate(hdul):
                if getattr(h, 'data', None) is not None:
                    data = h.data
                    print(f"  found data in HDU {i}: dtype={data.dtype}, shape={data.shape}")
                    arr = np.array(data)
                    print(f"  min: {np.nanmin(arr)}, max: {np.nanmax(arr)}, mean: {np.nanmean(arr)}")
                    print(f"  nans: {np.isnan(arr).sum()} / {arr.size}")
                    found = True
                    break
            if not found:
                print("  No data array found in any HDU")
    except Exception as e:
        print("  ERROR reading FITS:", e)
        traceback.print_exc()


def inspect_png(path: Path):
    print(f"Inspecting PNG: {path}")
    if not path.exists():
        print("  MISSING")
        return
    print(f"  size_bytes: {path.stat().st_size}")
    try:
        img = Image.open(path)
        print(f"  mode: {img.mode}, size: {img.size}")
    except Exception as e:
        print("  ERROR reading PNG:", e)
        traceback.print_exc()


def run_legacy_fits(ra, dec, size_arcmin, band):
    dc = DesCutout()
    filename = f"{ra:.5f}_{dec:.5f}_{band}.fits"
    out = OUT_DIR.joinpath("legacy_" + filename)
    print(f"Running legacy FITS: {out}")
    try:
        res = dc.single_cutout_fits(ra=ra, dec=dec, size_arcmin=size_arcmin, band=band, path=out)
        print("  produced:", res)
        inspect_fits(out)
    except Exception as e:
        print("  legacy FITS failed:", e)
        traceback.print_exc()


def run_legacy_png(ra, dec, size_arcmin, band):
    dc = DesCutout()
    filename = f"{ra:.5f}_{dec:.5f}.png"
    out = OUT_DIR.joinpath("legacy_" + filename)
    print(f"Running legacy PNG: {out}")
    try:
        res = dc.single_cutout_png(ra=ra, dec=dec, size_arcmin=size_arcmin, band=band, path=out)
        print("  produced:", res)
        inspect_png(out)
    except Exception as e:
        print("  legacy PNG failed:", e)
        traceback.print_exc()


def run_engine(engine_name, stencil, band, fmt, files=None):
    print(f"Running engine {engine_name} format={fmt} band={band}")
    from cutout.service.cutout_engine import create_cutout_engine

    engine = create_cutout_engine(engine_name)
    filename = f"engine_{engine_name}_{stencil['center']['ra']:.5f}_{stencil['center']['dec']:.5f}.{fmt}"
    out = OUT_DIR.joinpath(filename)
    try:
        # If no files provided, try to discover and uncompress via DesCutout
        if not files:
            try:
                dc = DesCutout()
                verts = dc.get_cutout_verts(stencil["center"]["ra"], stencil["center"]["dec"], stencil["radius"])  # type: ignore
                # If band is multiple letters (e.g. 'gri'), build mapping per band
                if isinstance(band, str) and len(band) > 1 and "," not in band and " " not in band:
                    bands = list(band)
                else:
                    # split by comma or space if present
                    if isinstance(band, str) and "," in band:
                        bands = [b.strip() for b in band.split(",") if b.strip()]
                    elif isinstance(band, str) and " " in band:
                        bands = [b.strip() for b in band.split() if b.strip()]
                    else:
                        bands = [band]

                if len(bands) == 1:
                    comp_files = dc.get_fits_files(verts, bands[0])
                    files = []
                    for comp in comp_files:
                        fits_filename = comp.name.split(".fz")[0]
                        uncompressed = dc.tmp_path.joinpath(fits_filename)
                        if not uncompressed.exists():
                            print(f"  uncompressing {comp} -> {uncompressed}")
                            try:
                                dc.funpack(comp, uncompressed)
                            except Exception as e:
                                print("  funpack failed:", e)
                        if uncompressed.exists():
                            files.append(str(uncompressed))
                else:
                    files_map = {}
                    for b in bands:
                        comp_files = dc.get_fits_files(verts, b)
                        files_map[b] = []
                        for comp in comp_files:
                            fits_filename = comp.name.split(".fz")[0]
                            uncompressed = dc.tmp_path.joinpath(fits_filename)
                            if not uncompressed.exists():
                                print(f"  uncompressing {comp} -> {uncompressed}")
                                try:
                                    dc.funpack(comp, uncompressed)
                                except Exception as e:
                                    print("  funpack failed:", e)
                            if uncompressed.exists():
                                files_map[b].append(str(uncompressed))
                    files = files_map
            except Exception:
                files = files or []

        print('  input_files passed to engine:', files)
        # Build extra kwargs (e.g., color/rgb_bands) for multi-band PNG tests
        extra_kwargs = {}
        if engine_name == 'astrocut' and fmt == 'png' and isinstance(band, str) and len(band) > 1 and ',' not in band and ' ' not in band:
            extra_kwargs['color'] = True
            extra_kwargs['rgb_bands'] = band

        res = engine.run_cutout(
            source_id="des_dr2",
            stencil=stencil,
            input_files=files,
            band=band,
            output_format=fmt,
            output_path=out,
            **extra_kwargs,
        )
        print("  produced:", res)
        if fmt == "fits":
            inspect_fits(out)
        else:
            inspect_png(out)
    except Exception as e:
        print(f"  engine {engine_name} failed:", e)
        traceback.print_exc()


def main():
    # Coordinates from examples
    cutouts = [
        {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "g", "format": "fits"},
        {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "gri", "format": "png"},
        {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "g", "format": "fits"},
        {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "gri", "format": "png"},
    ]

    for c in cutouts:
        ra = c["ra"]
        dec = c["dec"]
        size = c["size"]
        band = c["band"]
        fmt = c["format"]

        print("\n=== Test case ===")
        print(c)

        if fmt == "fits":
            # legacy path
            run_legacy_fits(ra, dec, size, band)
            # engine path (des engine)
            stencil = {"type": "circle", "center": {"ra": ra, "dec": dec}, "radius": size}
            run_engine("legacy", stencil, band, "fits")
            try:
                run_engine("astrocut", stencil, band, "fits")
            except Exception:
                pass

        elif fmt == "png":
            # legacy PNG
            run_legacy_png(ra, dec, size, band)
            # engine mono PNG (if band is single)
            stencil = {"type": "circle", "center": {"ra": ra, "dec": dec}, "radius": size}
            if len(band) == 1:
                run_engine("legacy", stencil, band, "png")
                run_engine("astrocut", stencil, band, "png")
            else:
                # multi-band: let run_engine perform discovery/uncompress for each band
                run_engine("legacy", stencil, band, "png", files=None)
                run_engine("astrocut", stencil, band, "png", files=None)


if __name__ == "__main__":
    main()
