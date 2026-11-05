"""One-period waveform tables for regenerated analog output."""
from __future__ import annotations

from typing import Tuple

import numpy as np

from .errors import ConfigError

KINDS = ("sine", "square", "triangle", "dc")


def one_period(kind: str, freq: float, sample_rate: float, amplitude: float = 1.0,
               offset: float = 0.0, duty: float = 0.5) -> Tuple[np.ndarray, float]:
    """Return (samples, actual_freq) holding exactly one period.

    The period length is rounded to an integer number of samples so the table can be
    regenerated without a phase jump, which shifts the output frequency slightly.
    """
    if kind not in KINDS:
        raise ConfigError(f"unknown waveform {kind!r}")
    if kind == "dc":
        return np.full(2, offset), float(sample_rate) / 2
    if freq <= 0 or sample_rate <= 0:
        raise ConfigError("freq and sample_rate must be positive")
    n = int(round(sample_rate / freq))
    # Two samples per period would make a sine all zeros, so require at least four.
    if n < 4:
        raise ConfigError("sample_rate must be at least 4x the waveform frequency")
    phase = np.arange(n) / n
    if kind == "sine":
        y = np.sin(2 * np.pi * phase)
    elif kind == "square":
        y = np.where(phase < duty, 1.0, -1.0)
    else:
        y = 4 * np.abs(phase - np.floor(phase + 0.75) + 0.25) - 1
    return amplitude * y + offset, sample_rate / n
