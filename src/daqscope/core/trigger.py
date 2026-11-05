from __future__ import annotations

import numpy as np


def find_edges(x: np.ndarray, level: float, slope: str = "rising", hysteresis: float = 0.0,
               state: int = 0, return_state: bool = False):
    """Fractional sample positions where x crosses level.

    A rising edge is reported once x has been below level-hysteresis and then reaches level,
    which keeps noise around the level from retriggering. Positions are linearly interpolated
    between the two samples that bracket the crossing, so the result is sub-sample accurate.

    state is the arming state carried in from the previous call (-1 armed, +1 above, 0 unknown).
    With return_state=True the state at the last sample is returned as well, so a long record can
    be searched piece by piece when each piece starts on the last sample of the one before.
    """
    x = np.asarray(x, dtype=float)
    if slope == "falling":
        x, level = -x, -level
    elif slope != "rising":
        raise ValueError(f"unknown slope {slope!r}")
    if x.size < 2:
        return (np.empty(0), state) if return_state else np.empty(0)
    st = np.zeros(x.size, dtype=np.int8)
    st[x >= level] = 1
    st[x < level - hysteresis] = -1
    # carry the last definite state (above / below) forward through the dead band
    last = np.maximum.accumulate(np.where(st != 0, np.arange(x.size), -1))
    carried = np.where(last >= 0, st[np.maximum(last, 0)], state)
    hits = np.nonzero((st[1:] == 1) & (carried[:-1] == -1))[0] + 1
    x0, x1 = x[hits - 1], x[hits]
    edges = hits - 1 + (level - x0) / (x1 - x0)
    return (edges, int(carried[-1])) if return_state else edges


def auto_hysteresis(x: np.ndarray) -> float:
    """Trigger hysteresis that rejects the noise on x: the 6-sigma peak-to-peak noise width.

    Noise sigma comes from the median absolute deviation of the second difference, which
    cancels a slowly varying signal and ignores outliers. The result is capped at 40 % of the
    peak-to-peak range of x so that a real edge can still arm the trigger.
    """
    x = np.asarray(x, dtype=float)
    if x.size < 8:
        return 0.0
    d2 = x[2:] - 2 * x[1:-1] + x[:-2]
    sigma = 1.4826 * np.median(np.abs(d2 - np.median(d2))) / np.sqrt(6.0)
    return float(min(6.0 * sigma, 0.4 * (x.max() - x.min())))
