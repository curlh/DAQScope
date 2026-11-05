from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Thread-safe ring buffer of shape (n_channels, capacity).

    The acquisition thread writes blocks and the GUI thread reads the latest samples.
    """

    def __init__(self, n_channels: int, capacity: int):
        self._data = np.zeros((n_channels, capacity))
        self._cap = capacity
        self._total = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def total_written(self) -> int:
        return self._total

    def write(self, block: np.ndarray) -> None:
        n = block.shape[1]
        if n >= self._cap:
            block = block[:, -self._cap:]
            n = self._cap
        with self._lock:
            pos = self._total % self._cap
            first = min(n, self._cap - pos)
            self._data[:, pos:pos + first] = block[:, :first]
            if first < n:
                self._data[:, :n - first] = block[:, first:]
            self._total += n

    def latest(self, n: int) -> np.ndarray:
        """Copy of the newest n samples (fewer if less has been written)."""
        with self._lock:
            n = min(n, self._total, self._cap)
            idx = np.arange(self._total - n, self._total) % self._cap
            return self._data[:, idx]   # fancy indexing already copies

    def window(self, start: int):
        """Samples from absolute index start up to now, and the total at that moment.

        Reading the total and the data under one lock keeps absolute indices consistent
        while the acquisition thread keeps writing. Returns None if start was overwritten.
        """
        with self._lock:
            total = self._total
            if start < total - self._cap or start > total:
                return None
            idx = np.arange(start, total) % self._cap
            return self._data[:, idx], total
