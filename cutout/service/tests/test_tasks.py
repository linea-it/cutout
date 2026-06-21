from pathlib import Path

import pytest

from cutout.service.tasks import _validate_input_files


def test_validate_input_files_accepts_none() -> None:
    _validate_input_files(None)


def test_validate_input_files_accepts_existing_file(tmp_path: Path) -> None:
    existing_file = tmp_path / "tile.fits.fz"
    existing_file.write_text("ok", encoding="utf-8")

    _validate_input_files([str(existing_file)])


def test_validate_input_files_raises_for_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.fits.fz"

    with pytest.raises(FileNotFoundError, match="Input file unavailable"):
        _validate_input_files([str(missing_file)])
