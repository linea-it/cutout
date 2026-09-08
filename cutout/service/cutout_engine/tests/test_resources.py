from __future__ import annotations

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from reproject import reproject_interp

from cutout.service.cutout_engine.astrocut_engine import _accumulate_hdu, _bin_factor, _output_window, output_grid
from cutout.service.cutout_engine.resources import (
    detect_limits,
    estimate_band_memory_bytes,
    plan_band_execution,
    split_threads,
)


def test_bin_factor_preview_vs_native() -> None:
    native = 7.305555555556e-05
    _wcs, _ny, _nx, out_scale = output_grid(
        SkyCoord(0.5 * u.deg, 0.017 * u.deg, frame="icrs"),
        2 * (21.104 / 60) * u.deg,
        native,
        max_dim=4096,
    )
    assert _bin_factor(native, out_scale) >= 2
    assert _bin_factor(native, native) == 1


def test_split_threads_production_rgb() -> None:
    assert split_threads(8, 3) == [3, 3, 2]


def test_split_threads_local_two_bands() -> None:
    assert split_threads(2, 2) == [1, 1]


def test_split_threads_single() -> None:
    assert split_threads(8, 1) == [8]


def test_output_grid_caps_png_side() -> None:
    center = SkyCoord(0.5 * u.deg, 0.017 * u.deg, frame="icrs")
    native = 7.305555555556e-05
    cutout_size = 2 * (21.104 / 60) * u.deg
    _wcs, ny, nx, _scale = output_grid(center, cutout_size, native, max_dim=None)
    assert max(ny, nx) > 4096
    capped_wcs, cny, cnx, cscale = output_grid(center, cutout_size, native, max_dim=4096)
    assert max(cny, cnx) <= 4096
    assert cscale > native
    assert capped_wcs.wcs.crval[0] == 0.5


def test_output_grid_thirty_arcmin_png_cap() -> None:
    center = SkyCoord(0.5 * u.deg, 0.017 * u.deg, frame="icrs")
    native = 7.305555555556e-05
    cutout_size = 2 * 0.5 * u.deg
    _wcs, ny, nx, _scale = output_grid(center, cutout_size, native, max_dim=4096)
    assert max(ny, nx) <= 4096
    assert min(ny, nx) >= 4090


def test_plan_clamps_to_cgroup(monkeypatch) -> None:
    monkeypatch.setattr("cutout.service.cutout_engine.resources.read_cgroup_cpus", lambda: 2)
    monkeypatch.setattr(
        "cutout.service.cutout_engine.resources.read_cgroup_memory_bytes",
        lambda: 8 * 1024 * 1024 * 1024,
    )
    monkeypatch.setattr("cutout.service.cutout_engine.resources._django_setting", lambda name, default: 0)
    plan = plan_band_execution(n_bands=3, ny=4096, nx=4096, n_tiles=2, max_band_workers=3)
    assert plan.cpus == 2
    assert plan.concurrent_bands == 2
    assert plan.threads_per_wave == (1, 1)
    assert plan.memory_budget_bytes <= int(8 * 1024 * 1024 * 1024 * 0.75)


def test_plan_production_three_bands(monkeypatch) -> None:
    monkeypatch.setattr("cutout.service.cutout_engine.resources.read_cgroup_cpus", lambda: 8)
    monkeypatch.setattr(
        "cutout.service.cutout_engine.resources.read_cgroup_memory_bytes",
        lambda: 32 * 1024 * 1024 * 1024,
    )
    monkeypatch.setattr("cutout.service.cutout_engine.resources._django_setting", lambda name, default: 0)
    plan = plan_band_execution(n_bands=3, ny=4096, nx=4096, n_tiles=4, max_band_workers=3)
    assert plan.cpus == 8
    assert plan.concurrent_bands == 3
    assert plan.threads_per_wave == (3, 3, 2)


def test_plan_memory_fallback_to_one_band(monkeypatch) -> None:
    monkeypatch.setattr("cutout.service.cutout_engine.resources.read_cgroup_cpus", lambda: 8)
    monkeypatch.setattr(
        "cutout.service.cutout_engine.resources.read_cgroup_memory_bytes",
        lambda: 512 * 1024 * 1024,
    )
    monkeypatch.setattr("cutout.service.cutout_engine.resources._django_setting", lambda name, default: 0)
    plan = plan_band_execution(n_bands=3, ny=4096, nx=4096, n_tiles=4, max_band_workers=3)
    assert plan.concurrent_bands == 1
    assert plan.threads_per_wave == (8,)


def test_estimate_band_memory_grows_with_grid() -> None:
    small = estimate_band_memory_bytes(128, 128, 1)
    large = estimate_band_memory_bytes(4096, 4096, 4)
    assert large > small


def test_detect_limits_override_cannot_exceed_cgroup(monkeypatch) -> None:
    monkeypatch.setattr("cutout.service.cutout_engine.resources.read_cgroup_cpus", lambda: 2)
    monkeypatch.setattr(
        "cutout.service.cutout_engine.resources.read_cgroup_memory_bytes",
        lambda: 8 * 1024 * 1024 * 1024,
    )

    def fake_setting(name: str, default: int) -> int:
        if name == "CUTOUT_PARALLEL_WORKERS":
            return 64
        if name == "CUTOUT_TASK_MEMORY_BUDGET_MB":
            return 99_999
        return default

    monkeypatch.setattr("cutout.service.cutout_engine.resources._django_setting", fake_setting)
    limits = detect_limits()
    assert limits.cpus == 2
    assert limits.memory_budget_bytes <= int(8 * 1024 * 1024 * 1024 * 0.75)


def _wcs_hdu(*, ny: int, nx: int, crval, scale: float, value: float, shift_pix=(0.0, 0.0)) -> fits.PrimaryHDU:
    data = np.full((ny, nx), value, dtype=np.float32)
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = nx
    header["NAXIS2"] = ny
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRVAL1"] = crval[0]
    header["CRVAL2"] = crval[1]
    header["CRPIX1"] = nx / 2.0 + shift_pix[0]
    header["CRPIX2"] = ny / 2.0 + shift_pix[1]
    header["CDELT1"] = -scale
    header["CDELT2"] = scale
    header["RADESYS"] = "ICRS"
    header["EQUINOX"] = 2000.0
    return fits.PrimaryHDU(data=data, header=header)


def test_window_reproject_matches_full_grid() -> None:
    scale = 0.01
    center = SkyCoord(10.0 * u.deg, -5.0 * u.deg, frame="icrs")
    cutout_size = 0.4 * u.deg
    hdu = _wcs_hdu(ny=16, nx=16, crval=(10.0, -5.0), scale=scale, value=7.0)
    out_wcs, ny, nx, _scale = output_grid(center, cutout_size, scale, max_dim=None)
    out_wcs.pixel_shape = (nx, ny)

    full = reproject_interp(hdu, out_wcs, shape_out=(ny, nx), order="bilinear", return_footprint=False)
    if isinstance(full, tuple):
        full = full[0]

    sum_arr = np.zeros((ny, nx), dtype=np.float32)
    count_arr = np.zeros((ny, nx), dtype=np.uint16)
    _accumulate_hdu(hdu, out_wcs=out_wcs, ny=ny, nx=nx, sum_arr=sum_arr, count_arr=count_arr, workers=1)
    windowed = np.divide(sum_arr, count_arr, out=np.full_like(sum_arr, np.nan), where=count_arr > 0)

    finite = np.isfinite(full) & np.isfinite(windowed)
    assert finite.any()
    np.testing.assert_allclose(full[finite], windowed[finite], rtol=1e-4, atol=1e-4)
    window = _output_window(hdu, out_wcs, ny, nx)
    assert window is not None
    y0, y1, x0, x1 = window
    assert (y1 - y0) * (x1 - x0) < ny * nx
