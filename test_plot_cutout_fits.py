#!/usr/bin/env python3
"""Inspect and plot a FITS cutout file.

Examples:
  python test_plot_cutout_fits.py --file /tmp/sync_result_test.fits

  python test_plot_cutout_fits.py \
    --file /tmp/sync_result_test.fits \
    --save /tmp/sync_result_test.png \
    --no-show

  python test_plot_cutout_fits.py --file /tmp/sync_result_test.fits --wcs
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


def _find_image_hdu(
    hdul: fits.HDUList, preferred_ext: int | None
) -> tuple[int, fits.hdu.base.ExtensionHDU | fits.PrimaryHDU]:
    if preferred_ext is not None:
        hdu = hdul[preferred_ext]
        if hdu.data is None:
            raise ValueError(f"HDU {preferred_ext} has no data")
        return preferred_ext, hdu

    for idx, hdu in enumerate(hdul):
        if hdu.data is not None and getattr(hdu.data, "ndim", 0) >= 2:
            return idx, hdu

    raise ValueError("No image HDU found in FITS file")


def _print_stats(data: np.ndarray, hdu_index: int) -> None:
    finite_mask = np.isfinite(data)
    finite_count = int(np.count_nonzero(finite_mask))
    total_count = int(data.size)

    print(f"HDU index: {hdu_index}")
    print(f"Shape: {data.shape}")
    print(f"dtype: {data.dtype}")
    print(f"Finite pixels: {finite_count}/{total_count}")

    if finite_count == 0:
        print("No finite pixels available for stats")
        return

    finite = data[finite_mask]
    print(f"Min: {float(np.min(finite)):.6g}")
    print(f"Max: {float(np.max(finite)):.6g}")
    print(f"Mean: {float(np.mean(finite)):.6g}")
    print(f"Median: {float(np.median(finite)):.6g}")


def _plot_image(
    data: np.ndarray, header: fits.Header, use_wcs: bool, title: str, save_path: Path | None, show: bool
) -> None:
    vmin, vmax = np.nanpercentile(data, [1, 99])

    if use_wcs:
        wcs = WCS(header)
        fig = plt.figure(figsize=(8, 7))
        ax = fig.add_subplot(111, projection=wcs)
        ax.set_xlabel("RA")
        ax.set_ylabel("Dec")
    else:
        fig, ax = plt.subplots(figsize=(8, 7))
        ax.set_xlabel("X pixel")
        ax.set_ylabel("Y pixel")

    image = ax.imshow(data, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
    ax.set_title(title)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Flux")
    fig.tight_layout()

    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"Plot saved to: {save_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and plot a FITS cutout")
    parser.add_argument("--file", required=True, help="Path to FITS file")
    parser.add_argument("--ext", type=int, default=None, help="HDU extension index (default: first image HDU)")
    parser.add_argument("--wcs", action="store_true", help="Use WCS projection when available")
    parser.add_argument("--save", default=None, help="Save plot image path (PNG, JPG, etc.)")
    parser.add_argument("--no-show", action="store_true", help="Do not open interactive plot window")
    args = parser.parse_args()

    fits_path = Path(args.file)
    if not fits_path.exists():
        raise FileNotFoundError(f"FITS file does not exist: {fits_path}")

    with fits.open(fits_path) as hdul:
        hdu_index, hdu = _find_image_hdu(hdul, args.ext)
        data = np.asarray(hdu.data, dtype=float)
        if data.ndim > 2:
            data = np.squeeze(data)
        if data.ndim != 2:
            raise ValueError(f"Expected a 2D image after squeeze, got shape={data.shape}")

        _print_stats(data, hdu_index)
        _plot_image(
            data=data,
            header=hdu.header,
            use_wcs=args.wcs,
            title=f"Cutout: {fits_path.name}",
            save_path=Path(args.save) if args.save else None,
            show=not args.no_show,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
