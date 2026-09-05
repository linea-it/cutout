from pathlib import Path

import pytest

from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine


def test_astrocut_engine_calls_fits_cut(monkeypatch):
    import numpy as np

    import cutout.service.cutout_engine.astrocut_engine as astro_module

    captured = {}

    def dummy_fits_cut(**kwargs):
        captured.update(kwargs)
        mock_hdu = astro_module.fits.PrimaryHDU(data=np.zeros((10, 10)))
        return [astro_module.fits.HDUList([mock_hdu])]

    monkeypatch.setattr(astro_module, "fits_cut", dummy_fits_cut)

    engine = AstrocutEngine()
    result = engine.run_cutout(
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.1},
        input_files=["/data/tiles/a.fits.fz"],
        band="g",
        output_format="fits",
        output_path="/tmp/out.fits",
    )

    assert result == Path("/tmp/out.fits")
    assert captured["input_files"] == ["/data/tiles/a.fits.fz"]
    assert captured["single_outfile"] is True
    assert captured["memory_only"] is True


def _wcs_hdu(module, value: float, ny: int = 32, nx: int = 32, scale: float = 7.305555555556e-05):
    import numpy as np

    data = np.full((ny, nx), value, dtype=np.float32)
    header = module.fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = nx
    header["NAXIS2"] = ny
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRVAL1"] = 1.0
    header["CRVAL2"] = 2.0
    header["CRPIX1"] = nx / 2.0
    header["CRPIX2"] = ny / 2.0
    header["CDELT1"] = -scale
    header["CDELT2"] = scale
    header["RADESYS"] = "ICRS"
    header["EQUINOX"] = 2000.0
    return module.fits.PrimaryHDU(data=data, header=header)


def test_png_respects_max_dim(tmp_path, monkeypatch):
    from PIL import Image

    import cutout.service.cutout_engine.astrocut_engine as astro_module

    in_fits = tmp_path / "a.fits"
    _wcs_hdu(astro_module, 12.0).writeto(in_fits)

    def boom(**kwargs):
        raise AssertionError("PNG preview must not call fits_cut")

    monkeypatch.setattr(astro_module, "fits_cut", boom)
    monkeypatch.setattr(
        astro_module,
        "_setting",
        lambda name, default: 64 if name == "CUTOUT_PNG_MAX_DIM" else default,
    )

    engine = AstrocutEngine()
    out_png = tmp_path / "capped.png"
    engine.run_cutout(
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.05},
        input_files=[str(in_fits)],
        band="g",
        output_format="png",
        output_path=out_png,
    )
    with Image.open(out_png) as img:
        assert max(img.size) <= 64


def test_fits_multi_tile_keeps_native_scale(tmp_path, monkeypatch):
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    import cutout.service.cutout_engine.astrocut_engine as astro_module

    scale = 7.305555555556e-05

    def dummy_fits_cut(**kwargs):
        return [astro_module.fits.HDUList([_wcs_hdu(astro_module, 5.0, scale=scale)])]

    monkeypatch.setattr(astro_module, "fits_cut", dummy_fits_cut)
    input_paths = [tmp_path / "a.fits", tmp_path / "b.fits"]
    for input_path in input_paths:
        _wcs_hdu(astro_module, 5.0, scale=scale).writeto(input_path)

    engine = AstrocutEngine()
    out = tmp_path / "mosaic.fits"
    engine.run_cutout(
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.02},
        input_files=[str(path) for path in input_paths],
        band="g",
        output_format="fits",
        output_path=out,
    )
    with fits.open(out) as hdul:
        wcs = WCS(hdul[0].header)
        native = abs(wcs.proj_plane_pixel_scales()[0].to_value("deg"))
        np.testing.assert_allclose(native, scale, rtol=1e-3)
        assert max(hdul[0].data.shape) > 64


def test_astrocut_engine_rejects_unsupported_format() -> None:
    engine = AstrocutEngine()

    with pytest.raises(ValueError, match="supports only fits"):
        engine.run_cutout(
            source_id="des_dr2",
            stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.1},
            input_files=["/data/tiles/a.fits.fz"],
            band="g",
            output_format="jpg",
            output_path="/tmp/out.jpg",
        )


def test_astrocut_engine_requires_input_files() -> None:
    engine = AstrocutEngine()

    with pytest.raises(ValueError, match="requires at least one input file"):
        engine.run_cutout(
            source_id="des_dr2",
            stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.1},
            input_files=[],
            band="g",
            output_format="fits",
            output_path="/tmp/out.fits",
        )
