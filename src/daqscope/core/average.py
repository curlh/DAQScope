from __future__ import annotations

from collections import deque
from typing import Deque, Optional

import numpy as np

from .scope import ScopeFrame


class FrameAverager:
    """Rolling average of triggered frames.

    Each frame is resampled onto the common grid by its interpolated trigger offset first, so the
    trigger point stays sharp. n = 1 passes frames through. Untriggered and rolling frames are
    passed through and restart the average.
    """

    def __init__(self, n: int = 1):
        self.n = n
        self._frames: Deque[np.ndarray] = deque()
        self._sum: Optional[np.ndarray] = None

    def reset(self, n: Optional[int] = None) -> None:
        if n is not None:
            self.n = n
        self._frames.clear()
        self._sum = None

    def add(self, fr: ScopeFrame) -> ScopeFrame:
        if self.n <= 1 or not fr.triggered or fr.rolling:
            self.reset()
            return fr
        k = np.arange(fr.data.shape[1])
        aligned = np.vstack([np.interp(k + fr.frac, k, row) for row in fr.data])
        if self._sum is not None and self._sum.shape != aligned.shape:
            self.reset()
        self._frames.append(aligned)
        self._sum = aligned.copy() if self._sum is None else self._sum + aligned
        while len(self._frames) > self.n:
            self._sum -= self._frames.popleft()
        return ScopeFrame(self._sum / len(self._frames), fr.sample_rate, fr.pre, 0.0, True, False)
