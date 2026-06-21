import pytest

from cutout.service.cutout_engine import AstrocutEngine, DesCutoutEngine, create_cutout_engine


def test_factory_returns_astrocut_engine() -> None:
    engine = create_cutout_engine("astrocut")
    assert isinstance(engine, AstrocutEngine)


def test_factory_returns_legacy_engine() -> None:
    engine = create_cutout_engine("legacy")
    assert isinstance(engine, DesCutoutEngine)


def test_factory_rejects_unknown_engine() -> None:
    with pytest.raises(ValueError, match="Unsupported cutout engine"):
        create_cutout_engine("unknown")
