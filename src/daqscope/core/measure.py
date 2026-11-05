from __future__ import annotations

from typing import Dict

import numpy as np

from .trigger import find_edges


def measure(y: np.ndarray, sample_rate: float) -> Dict[str, float]:
    """Automatic measurements on one trace. Missing values are NaN."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    out = {k: float("nan") for k in ("max", "min", "pp", "mean", "rms", "freq", "period", "duty")}
    if y.size == 0:
        return out
    vmax, vmin = float(y.max()), float(y.min())
    out.update({"max": vmax, "min": vmin, "pp": vmax - vmin, "mean": float(y.mean()),
                "rms": float(np.sqrt(np.mean(y ** 2)))})
    span = vmax - vmin
    if span <= 0:
        return out
    # 50 % crossings, armed from the 10 % level (the usual 10/90 reference levels)
    mid = vmin + 0.5 * span
    hyst = 0.4 * span
    rise = find_edges(y, mid, "rising", hyst)
    fall = find_edges(y, mid, "falling", hyst)
    # Two cycles with the edges on the record border leave only one rising edge inside it, so
    # fall back to the falling edges for the period. Duty cycle still needs two rising edges.
    edges = rise if rise.size >= 2 else fall
    if edges.size >= 2:
        period = float(np.mean(np.diff(edges))) / sample_rate
        out["period"], out["freq"] = period, 1.0 / period
    if rise.size >= 2:
        widths = []
        for a, b in zip(rise[:-1], rise[1:]):
            f = fall[(fall > a) & (fall < b)]
            if f.size:
                widths.append((f[0] - a) / (b - a))
        if widths:
            out["duty"] = float(np.mean(widths))
    return out
