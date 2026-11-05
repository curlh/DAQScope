from __future__ import annotations

from typing import Sequence

import numpy as np

from .config import AIChannel


def apply_scales(data: np.ndarray, channels: Sequence[AIChannel]) -> np.ndarray:
    """Apply each channel's linear scale to data of shape (n_channels, n_samples)."""
    gains = np.array([c.scale.gain for c in channels])[:, None]
    offsets = np.array([c.scale.offset for c in channels])[:, None]
    if np.all(gains == 1.0) and np.all(offsets == 0.0):
        return data
    return data * gains + offsets
