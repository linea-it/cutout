from pathlib import Path

import numpy as np
from astropy.io import fits

from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine


def _hdulist(value: float, shape=(64, 64)) -> fits.HDUList:
    data = np.full(shape, value, dtype=np.float32)
    return fits.HDUList([fits.PrimaryHDU(data=data)])


def test_mono_png(tmp_path, monkeypatch):
    def mock_fits_cut(input_files, coordinates, cutout_size, single_outfile=True, memory_only=True):
        return [_hdulist(42)]

    monkeypatch.setattr("cutout.service.cutout_engine.astrocut_engine.fits_cut", mock_fits_cut)

    engine = AstrocutEngine()
    stencil = {"type": "circle", "center": {"ra": 36.0, "dec": -10.0}, "radius": 1.0}
    out_png = tmp_path / "out.png"
    res = engine.run_cutout(
        source_id="des_dr2",
        stencil=stencil,
        input_files=[str(tmp_path / "in.fits")],
        band="g",
        output_format="png",
        output_path=out_png,
    )

    assert Path(res).exists()
    assert Path(res).suffix == ".png"
    assert Path(res).stat().st_size > 0


def test_rgb_png(tmp_path, monkeypatch):
    band_values = {"g1": 50.0, "r1": 100.0, "i1": 150.0}

    def mock_fits_cut(input_files, coordinates, cutout_size, single_outfile=True, memory_only=True):
        stem = Path(str(input_files[0])).stem
        return [_hdulist(band_values.get(stem, 10.0))]

    monkeypatch.setattr("cutout.service.cutout_engine.astrocut_engine.fits_cut", mock_fits_cut)

    engine = AstrocutEngine()
    stencil = {"type": "circle", "center": {"ra": 36.0, "dec": -10.0}, "radius": 1.0}
    in_map = {"g": [str(tmp_path / "g1.fits")], "r": [str(tmp_path / "r1.fits")], "i": [str(tmp_path / "i1.fits")]}

    out_png = tmp_path / "out_rgb.png"
    res = engine.run_cutout(
        source_id="des_dr2",
        stencil=stencil,
        input_files=in_map,
        band="g",
        output_format="png",
        output_path=out_png,
        color=True,
        rgb_bands="gri",
    )

    assert Path(res).exists()
    assert Path(res).suffix == ".png"
    assert Path(res).stat().st_size > 0
