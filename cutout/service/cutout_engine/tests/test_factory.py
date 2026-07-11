import pytest

from cutout.service.cutout_engine import AstrocutEngine, create_cutout_engine


def test_factory_returns_astrocut_engine() -> None:
    engine = create_cutout_engine("astrocut")
    assert isinstance(engine, AstrocutEngine)


def test_factory_rejects_legacy_engine() -> None:
    with pytest.raises(ValueError, match="Unsupported cutout engine"):
        create_cutout_engine("legacy")


def test_factory_rejects_unknown_engine() -> None:
    with pytest.raises(ValueError, match="Unsupported cutout engine"):
        create_cutout_engine("unknown")
