from __future__ import annotations

from typing import Tuple

import numpy as np


def minmax_decimate(t: np.ndarray, y: np.ndarray, max_points: int) -> Tuple[np.ndarray, np.ndarray]:
    """Reduce a trace to about max_points while keeping every peak (peak-detect display).

    Each bin contributes its minimum and its maximum in time order, so narrow glitches stay
    visible after reduction, as on an oscilloscope in peak-detect mode.
    """
    n = y.size
    if n <= max_points or max_points < 2:
        return t, y
    # Bins of k samples. The last, shorter bin is kept; dropping the remainder of an uneven
    # division cut the right end off the trace.
    k = -(-n // (max_points // 2))
    full = n // k
    starts = np.arange(full) * k
    body = y[:full * k].reshape(full, k)
    i_min = starts + body.argmin(axis=1)
    i_max = starts + body.argmax(axis=1)
    if full * k < n:
        tail = y[full * k:]
        i_min = np.append(i_min, full * k + tail.argmin())
        i_max = np.append(i_max, full * k + tail.argmax())
    idx = np.empty(2 * i_min.size, dtype=np.int64)
    idx[0::2] = np.minimum(i_min, i_max)
    idx[1::2] = np.maximum(i_min, i_max)
    return t[idx], y[idx]
