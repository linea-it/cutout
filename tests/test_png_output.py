from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine, _sample_box_perimeter


def _write_image(path: Path, value: float, shape=(64, 64), wcs: bool = False) -> None:
    data = np.full(shape, value, dtype=np.float32)
    header = fits.Header()
    if wcs:
        ny, nx = shape
        header["NAXIS"] = 2
        header["NAXIS1"] = nx
        header["NAXIS2"] = ny
        header["CTYPE1"] = "RA---TAN"
        header["CTYPE2"] = "DEC--TAN"
        header["CRVAL1"] = 36.0
        header["CRVAL2"] = -10.0
        header["CRPIX1"] = nx / 2.0
        header["CRPIX2"] = ny / 2.0
        header["CDELT1"] = -0.01
        header["CDELT2"] = 0.01
        header["RADESYS"] = "ICRS"
        header["EQUINOX"] = 2000.0
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def test_mono_png(tmp_path):
    in_fits = tmp_path / "in.fits"
    _write_image(in_fits, 42.0, wcs=True)
    engine = AstrocutEngine()
    stencil = {"type": "circle", "center": {"ra": 36.0, "dec": -10.0}, "radius": 1.0}
    out_png = tmp_path / "out.png"
    res = engine.run_cutout(
        source_id="des_dr2",
        stencil=stencil,
        input_files=[str(in_fits)],
        band="g",
        output_format="png",
        output_path=out_png,
    )
    assert Path(res).exists()
    assert Path(res).suffix == ".png"
    assert Path(res).stat().st_size > 0


def test_png_without_wcs_is_rejected(tmp_path):
    in_fits = tmp_path / "no_wcs.fits"
    _write_image(in_fits, 42.0)
    engine = AstrocutEngine()

    with pytest.raises(ValueError, match="no valid celestial WCS"):
        engine.run_cutout(
            source_id="des_dr2",
            stencil={"type": "circle", "center": {"ra": 36.0, "dec": -10.0}, "radius": 0.1},
            input_files=[str(in_fits)],
            band="g",
            output_format="png",
            output_path=tmp_path / "invalid.png",
        )


def test_perimeter_sampling_is_adaptive():
    small_x, _small_y = _sample_box_perimeter(4096, 4096)
    large_x, large_y = _sample_box_perimeter(10000, 10000)

    assert len(small_x) == 4 * 17
    assert len(large_x) == len(large_y) == 4 * 41
    assert large_x.min() == large_y.min() == -0.5
    assert large_x.max() == large_y.max() == 9999.5


def test_rgb_png(tmp_path):
    paths = {}
    for name, value in (("g1", 50.0), ("r1", 100.0), ("i1", 150.0)):
        p = tmp_path / f"{name}.fits"
        _write_image(p, value, wcs=True)
        paths[name[0]] = [str(p)]

    engine = AstrocutEngine()
    stencil = {"type": "circle", "center": {"ra": 36.0, "dec": -10.0}, "radius": 0.2}
    out_png = tmp_path / "out_rgb.png"
    res = engine.run_cutout(
        source_id="des_dr2",
        stencil=stencil,
        input_files=paths,
        band="g",
        output_format="png",
        output_path=out_png,
        color=True,
        rgb_bands="gri",
    )
    assert Path(res).exists()
    assert Path(res).suffix == ".png"
    assert Path(res).stat().st_size > 0
