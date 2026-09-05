"""Grid-size checks for the 21' and 30' PNG cases. Live timing is opt-in."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord

from cutout.service.cutout_engine.astrocut_engine import output_grid

DES_PIXEL_SCALE_DEG = 7.305555555556e-05


@pytest.mark.parametrize("radius_arcmin", [21.104, 30.0])
def test_png_grid_for_large_radii(radius_arcmin: float) -> None:
    center = SkyCoord(0.5 * u.deg, 0.017 * u.deg, frame="icrs")
    cutout_size = 2 * (radius_arcmin / 60.0) * u.deg
    _wcs, ny, nx, _scale = output_grid(center, cutout_size, DES_PIXEL_SCALE_DEG, max_dim=4096)
    assert max(ny, nx) <= 4096
    assert min(ny, nx) >= 4000


@pytest.mark.skipif(not os.environ.get("CUTOUT_RUN_BENCHMARK"), reason="set CUTOUT_RUN_BENCHMARK=1 to run live tiles")
def test_live_local_rgb_21_arcmin(tmp_path: Path) -> None:
    from time import perf_counter

    from PIL import Image

    from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine

    g = Path("/data/tiles/des_dr2/DES0002+0001/DES0002+0001_r4907p01_g.fits.fz")
    r = Path("/data/tiles/des_dr2/DES0002+0001/DES0002+0001_r4907p01_r.fits.fz")
    i = Path("/data/tiles/des_dr2/DES0002+0001/DES0002+0001_r4907p01_i.fits.fz")
    g2 = Path("/data/tiles/des_dr2/DES0002-0041/DES0002-0041_r4907p01_g.fits.fz")
    r2 = Path("/data/tiles/des_dr2/DES0002-0041/DES0002-0041_r4907p01_r.fits.fz")
    i2 = Path("/data/tiles/des_dr2/DES0002-0041/DES0002-0041_r4907p01_i.fits.fz")
    if not all(p.exists() for p in (g, r, i, g2, r2, i2)):
        pytest.skip("local DES DR2 tiles not mounted")

    engine = AstrocutEngine()
    out = tmp_path / "bench_21.png"
    t0 = perf_counter()
    engine.run_cutout(
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": 0.5, "dec": 0.017}, "radius": 21.104 / 60.0},
        input_files={"g": [str(g), str(g2)], "r": [str(r), str(r2)], "i": [str(i), str(i2)]},
        band="g",
        output_format="png",
        output_path=out,
        color=True,
        rgb_bands="gri",
    )
    elapsed = perf_counter() - t0
    with Image.open(out) as img:
        assert max(img.size) <= 4096
    assert out.stat().st_size < 50 * 1024 * 1024
    assert elapsed < 180
