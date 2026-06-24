"""RGB color-composition for astronomical cutouts.

Two methods, one fundamental difference:

arcsinh_clip — per-band independent compression
    Each band is normalized and arcsinh-stretched separately.
    A pixel whose g-band value is faint will map to a dark blue,
    regardless of what r and i are doing.
    Result: high color contrast, saturated stars, dark background.
    Use when: you want each filter to determine its own fate.

lupton — shared-intensity compression (Lupton et al. 2004)
    All three bands are normalized, then the average intensity
    I = (R+G+B)/3 is computed. A single compression ratio f(I)/I
    is applied to all three bands equally.
    Result: preserves physical flux ratios between bands.
    Use when: you want color fidelity over contrast.

Why we do NOT use astropy's ``make_lupton_rgb``:
    It places ``stretch`` in the *denominator* of the arcsinh
    (``soften = Q / stretch``), which is the opposite of the
    Lupton et al. 2004 paper (``asinh(alpha * beta * I) / alpha``).
    After extensive testing, it cannot reproduce the behavior
    of either arcsinh_clip or the paper's own algorithm.
"""

from __future__ import annotations

import numpy as np

COLOR_PARAMS: dict[str, dict] = {
    "des_dr2": {
        "method": "lupton",
        "arcsinh_clip": {
            "g": (-1.2, 300.0, 80.0, 1.0),  # (black, white, contrast, gain)
            "r": (-1.2, 400.0, 80.0, 1.0),
            "i": (-1.2, 400.0, 80.0, 1.0),
            "z": (-1.2, 400.0, 80.0, 1.0),
            "Y": (-1.0, 350.0, 80.0, 1.0),
        },
        "lupton": {
            "Q": 10.0,
            "stretch": 8.0,
            "gain": 1.9,
            "g": (-1.2, 300),  # (sky, clip_range = white - sky)
            "r": (-1.2, 400),
            "i": (-1.2, 400),
            "z": (-1.2, 400),
            "Y": (-1.0, 350),
        },
    },
}


def compose_rgb(
    arrays: list[np.ndarray],
    bands: list[str],
    source_id: str,
) -> np.ndarray:
    """Dispatch to the color method configured for *source_id*."""
    params = COLOR_PARAMS.get(source_id)
    if params is None:
        raise ValueError(f"No color params for catalog {source_id}")

    method = params.get("method", "arcsinh_clip")
    if method == "arcsinh_clip":
        return _arcsinh_clip(arrays, bands, params["arcsinh_clip"])
    elif method == "lupton":
        return _lupton(arrays, bands, params["lupton"])
    raise ValueError(f"Unknown color method: {method}")


def _arcsinh_stretch(
    array: np.ndarray,
    black: float,
    white: float,
    contrast: float = 80.0,
    gain: float = 1.0,
) -> np.ndarray:
    """(pixel - black) / (white - black) → arcsinh(×contrast) / arcsinh(contrast) × gain."""
    scaled = np.clip((array - black) / (white - black), 0, 1)
    stretched = np.arcsinh(scaled * contrast) / np.arcsinh(contrast)
    return (stretched * gain * 255).clip(0, 255).astype(np.uint8)


def _arcsinh_clip(
    arrays: list[np.ndarray],
    bands: list[str],
    cfg: dict,
) -> np.ndarray:
    """Per-band arcsinh stretch, stacked as RGB."""
    chans = []
    for idx in [2, 1, 0]:
        black, white, contrast, gain = cfg[bands[idx]]
        chans.append(_arcsinh_stretch(arrays[idx], black, white, contrast, gain))
    return np.dstack(chans)


def _lupton(
    arrays: list[np.ndarray],
    bands: list[str],
    cfg: dict,
) -> np.ndarray:
    """Lupton et al. 2004: shared-intensity arcsinh with color-preserving ratio f(I)/I."""
    Q = cfg["Q"]
    stretch = cfg["stretch"]
    gain = cfg.get("gain", 1.0)

    # Per-band normalization to [0, 1]
    norm = []
    for i, b in enumerate(bands):
        sky, clip_range = cfg[b]
        s = np.clip(arrays[i], sky, sky + clip_range)
        s = (s - sky) / clip_range
        norm.append(s)

    # Lupton 2004: I = (R+G+B)/3, ratio = f(I)/I
    I = (norm[0] + norm[1] + norm[2]) / 3.0
    I = np.maximum(I, 1e-30)
    fI = np.arcsinh(I * stretch * Q) / Q
    ratio = np.clip(fI / I, 0, None)

    # Apply ratio + gain → uint8
    chans = []
    for idx in [2, 1, 0]:
        chans.append((norm[idx] * ratio * gain * 255).clip(0, 255).astype(np.uint8))
    return np.dstack(chans)
