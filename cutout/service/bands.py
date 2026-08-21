"""Path-safe band tokens (survey-agnostic).

Do not hardcode photometric band names here: each survey may expose a
different set (DES grizY, LSST ugrizy, etc.). Security only requires that a
band string cannot alter filesystem paths (no separators or ``..``).
"""

from __future__ import annotations

from pathlib import Path


def parse_rgb_band_list(raw: str) -> list[str]:
    """Parse rgb_bands accepting 'gri', 'g,r,i' or 'g r i'."""
    if "," in raw:
        return [b.strip() for b in raw.split(",") if b.strip()]
    if " " in raw:
        return [b.strip() for b in raw.split() if b.strip()]
    return list(raw)


def assert_safe_path_component(value: str, *, label: str) -> str:
    """Reject empty, dotted, or separator-containing path segments."""
    if not value or value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe {label}: {value!r}")
    return value


def assert_safe_band(band: str) -> str:
    """Ensure ``band`` is a single path-safe token (not a traversal payload)."""
    return assert_safe_path_component(band, label="band")


def assert_path_under_root(
    path: Path,
    root: Path,
    *,
    label: str = "root",
    follow_symlinks: bool = True,
) -> Path:
    """Ensure ``path`` stays under ``root`` (no ``..`` traversal).

    When ``follow_symlinks`` is True (default), the fully resolved target must
    stay under ``root`` — use this for result downloads.

    When False, only the parent directory is resolved. Leaf symlinks may point
    outside ``root`` (local ``des_dr2`` tiles are symlinks into ``Y6A1``). Path
    components are still validated separately via ``assert_safe_path_component``.
    """
    resolved_root = root.resolve()
    if follow_symlinks:
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(resolved_root):
            raise ValueError(f"Path escapes {label}: {resolved_path} (root={resolved_root})")
        return resolved_path

    resolved_parent = path.parent.resolve()
    if not resolved_parent.is_relative_to(resolved_root):
        raise ValueError(f"Path escapes {label}: {resolved_parent / path.name} (root={resolved_root})")
    return resolved_parent / path.name


# Cutout products only — never serve arbitrary paths from JobResult.file_path.
_DEFAULT_RESULTS_ROOT = Path("/data/results")


def get_results_root() -> Path:
    """Return configured results root (override in tests via CUTOUT_RESULTS_ROOT)."""
    try:
        from django.conf import settings

        configured = getattr(settings, "CUTOUT_RESULTS_ROOT", None)
        if configured:
            return Path(configured)
    except Exception:
        pass
    return _DEFAULT_RESULTS_ROOT


def assert_result_path(path: Path | str) -> Path:
    """Ensure a downloadable result path stays under the results root."""
    return assert_path_under_root(Path(path), get_results_root(), label="results root")
