from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from cutout.service.cutout_engine import astrocut_engine as astro_module
from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine, _orient_png_for_display


def _make_hdu(data, pixel_scale=0.001):
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [5.0, 5.0]
    wcs.wcs.crval = [1.0, 2.0]
    wcs.wcs.cd = [[-pixel_scale, 0.0], [0.0, pixel_scale]]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return fits.ImageHDU(data=data, header=wcs.to_header())


def test_astrocut_engine_calls_fits_cut(monkeypatch):
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


def test_mosaic_hdus_combines_aligned_tiles_without_reprojection(monkeypatch, tmp_path) -> None:
    def fail_reproject(*args, **kwargs):
        raise AssertionError("aligned tiles must not be reprojected")

    monkeypatch.setattr(astro_module, "reproject_interp", fail_reproject)
    data_hdus = [
        (0, _make_hdu(np.ones((4, 4), dtype="float32"))),
        (1, _make_hdu(np.full((4, 4), 3, dtype="float32"))),
    ]

    result = astro_module._mosaic_hdus(
        data_hdus,
        center=SkyCoord(1.0, 2.0, unit="deg"),
        cutout_size=0.004 * u.deg,
        input_files=["one.fits", "two.fits"],
        ref_header=data_hdus[0][1].header,
    )

    assert result.header["METHOD"] == "aligned-grid + nanmean"
    assert (result.data == 2).all()
    result.writeto(tmp_path / "aligned.fits")


def test_mosaic_hdus_reprojects_misaligned_tiles(monkeypatch) -> None:
    calls = []

    def dummy_reproject(hdu, out_wcs, shape_out, order):
        calls.append(hdu)
        return np.zeros(shape_out, dtype="float32"), None

    monkeypatch.setattr(astro_module, "reproject_interp", dummy_reproject)
    data_hdus = [
        (0, _make_hdu(np.ones((4, 4), dtype="float32"))),
        (1, _make_hdu(np.ones((4, 4), dtype="float32"), pixel_scale=0.0011)),
    ]

    result = astro_module._mosaic_hdus(
        data_hdus,
        center=SkyCoord(1.0, 2.0, unit="deg"),
        cutout_size=0.004 * u.deg,
        input_files=["one.fits", "two.fits"],
        ref_header=data_hdus[0][1].header,
    )

    assert len(calls) == 2
    assert result.header["METHOD"] == "reproject_interp + nanmean"


def test_png_orientation_moves_north_to_the_first_row():
    data = np.arange(12, dtype=np.float32).reshape(4, 3)
    header = _make_hdu(data).header
    header["CRPIX1"] = 2.0
    header["CRPIX2"] = 2.5

    oriented, new_header = _orient_png_for_display(data, header)

    assert np.array_equal(oriented, data[::-1])
    old_coord = WCS(header).pixel_to_world(0, data.shape[0] - 1)
    new_coord = WCS(new_header).pixel_to_world(0, 0)
    assert new_coord.ra.deg == pytest.approx(old_coord.ra.deg)
    assert new_coord.dec.deg == pytest.approx(old_coord.dec.deg)
    assert float(WCS(new_header).celestial.pixel_scale_matrix[1, 1]) < 0


def test_png_orientation_keeps_array_when_north_is_already_first_row():
    data = np.arange(12, dtype=np.float32).reshape(4, 3)
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [2.0, 2.5]
    wcs.wcs.crval = [1.0, 2.0]
    wcs.wcs.cd = [[-0.001, 0.0], [0.0, -0.001]]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]

    oriented, _new_header = _orient_png_for_display(data, wcs.to_header())

    assert np.array_equal(oriented, data)
