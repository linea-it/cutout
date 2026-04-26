from pathlib import Path

from cutout.service.cutout_engine.des_engine import DesCutoutEngine


class DummyCutout:
    def __init__(self, source_id, stencil, band, format):
        self.source_id = source_id
        self.stencil = stencil
        self.band = band
        self.format = format

    def create(self, output_path):
        return Path(output_path)


def test_des_cutout_engine_delegates_to_cutout(monkeypatch):
    import cutout.service.cutout_engine.des_engine as des_engine_module

    monkeypatch.setattr(des_engine_module, "Cutout", DummyCutout)

    engine = DesCutoutEngine()
    result = engine.run_cutout(
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": 10.0, "dec": -1.0}, "radius": 1.0},
        band="g",
        output_format="fits",
        output_path="/tmp/out.fits",
    )

    assert result == Path("/tmp/out.fits")
