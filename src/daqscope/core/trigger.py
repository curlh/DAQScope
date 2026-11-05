from __future__ import annotations

import numpy as np


def find_edges(x: np.ndarray, level: float, slope: str = "rising", hysteresis: float = 0.0) -> np.ndarray:
    """Fractional sample positions where x crosses level.

    A rising edge is reported once x has been below level-hysteresis and then reaches level,
    which keeps noise around the level from retriggering. Positions are linearly interpolated
    between the two samples that bracket the crossing, so the result is sub-sample accurate.
    """
    x = np.asarray(x, dtype=float)
    if slope == "falling":
        x, level = -x, -level
    elif slope != "rising":
        raise ValueError(f"unknown slope {slope!r}")
    if x.size < 2:
        return np.empty(0)
    state = np.zeros(x.size, dtype=np.int8)
    state[x >= level] = 1
    state[x < level - hysteresis] = -1
    # carry the last definite state (above / below) forward through the dead band
    last = np.maximum.accumulate(np.where(state != 0, np.arange(x.size), 0))
    carried = state[last]
    hits = np.nonzero((state[1:] == 1) & (carried[:-1] == -1))[0] + 1
    x0, x1 = x[hits - 1], x[hits]
    return hits - 1 + (level - x0) / (x1 - x0)
