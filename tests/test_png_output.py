import numpy as np
from pathlib import Path

from astropy.io import fits

from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine


def make_fits(path: Path, shape=(64, 64), value=1):
    data = np.full(shape, value, dtype=float)
    fits.writeto(path, data, overwrite=True)
    return str(path)


def test_mono_png(tmp_path, monkeypatch):
    in_fits = tmp_path / "in.fits"
    make_fits(in_fits, value=42)

    def mock_fits_cut(**kwargs):
        out = tmp_path / f"{kwargs.get('cutout_prefix','cut')}.fits"
        make_fits(out, value=42)
        return str(out)

    monkeypatch.setattr("cutout.service.cutout_engine.astrocut_engine.fits_cut", mock_fits_cut)

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


def test_rgb_png(tmp_path, monkeypatch):
    def mock_fits_cut(input_files, coordinates, cutout_size, single_outfile, cutout_prefix, output_dir):
        # produce file with value dependent on prefix suffix
        val = 10
        if cutout_prefix.endswith("_g"):
            val = 50
        elif cutout_prefix.endswith("_r"):
            val = 100
        elif cutout_prefix.endswith("_i"):
            val = 150
        out = Path(output_dir) / f"{cutout_prefix}.fits"
        make_fits(out, value=val)
        return str(out)

    monkeypatch.setattr("cutout.service.cutout_engine.astrocut_engine.fits_cut", mock_fits_cut)

    engine = AstrocutEngine()
    stencil = {"type": "circle", "center": {"ra": 36.0, "dec": -10.0}, "radius": 1.0}
    # prepare dummy original files (not used by mock but kept for clarity)
    in_map = {"g": [str(tmp_path / "g1.fits")], "r": [str(tmp_path / "r1.fits")], "i": [str(tmp_path / "i1.fits")]}
    for v in in_map.values():
        make_fits(Path(v[0]), value=1)

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
