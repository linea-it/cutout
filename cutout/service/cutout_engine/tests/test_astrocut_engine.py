from pathlib import Path

import pytest

from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine


def test_astrocut_engine_calls_fits_cut(monkeypatch):
    import cutout.service.cutout_engine.astrocut_engine as astro_module

    captured = {}

    def dummy_fits_cut(**kwargs):
        captured.update(kwargs)
        return "/tmp/generated.fits"

    moved = {}

    def dummy_move(src, dst):
        moved["src"] = src
        moved["dst"] = dst

    monkeypatch.setattr(astro_module, "fits_cut", dummy_fits_cut)
    monkeypatch.setattr(astro_module.shutil, "move", dummy_move)

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
    assert moved == {"src": "/tmp/generated.fits", "dst": "/tmp/out.fits"}


def test_astrocut_engine_rejects_non_fits() -> None:
    engine = AstrocutEngine()

    with pytest.raises(ValueError, match="supports only fits"):
        engine.run_cutout(
            source_id="des_dr2",
            stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.1},
            input_files=["/data/tiles/a.fits.fz"],
            band="g",
            output_format="png",
            output_path="/tmp/out.png",
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
