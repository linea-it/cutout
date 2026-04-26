from pathlib import Path

from cutout.service.cutout_engine.astrocut_engine import AstrocutEngine


def test_astrocut_engine_fallback_to_des(monkeypatch):
    import cutout.service.cutout_engine.astrocut_engine as astro_module

    class DummyDesCutoutEngine:
        def run_cutout(self, **kwargs):
            return Path("/tmp/fallback.fits")

    monkeypatch.setattr(astro_module, "DesCutoutEngine", DummyDesCutoutEngine)

    engine = AstrocutEngine()
    result = engine.run_cutout(
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": 1.0, "dec": 2.0}, "radius": 0.1},
        band="g",
        output_format="fits",
        output_path="/tmp/out.fits",
    )

    assert result == Path("/tmp/fallback.fits")
