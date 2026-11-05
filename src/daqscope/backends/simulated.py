"""Simulated device so the library, GUI and tests run without hardware.

SimDev1 mimics a small multifunction card: 8 AI, 2 AO, 8 DI and 8 DO lines, 2 counters.
AI channel k carries a sine at 10*(k+1) Hz with a little noise. Reads are paced in
real time so streaming code sees the same timing as on hardware.
"""
from __future__ import annotations

import re
import time
from typing import List, Sequence

import numpy as np

from ..core.config import (AIConfig, AOConfig, CounterConfig, DeviceInfo,
                           DIOConfig)
from ..core.errors import BackendError
from .base import (AnalogInputTask, AnalogOutputTask, Backend,
                   CounterInputTask, DigitalInputTask, DigitalOutputTask)

DEVICE = "SimDev1"
N_AI, N_AO, N_LINES, N_CTR = 8, 2, 8, 2
SIM_TONE_HZ = 10.0           # AI channel k has frequency SIM_TONE_HZ * (k + 1)
SIM_AMPLITUDE = 1.0          # volts
SIM_NOISE = 0.01             # volts RMS
SIM_PULSE_HZ = 1000.0        # counter input signal


def _index(name: str) -> int:
    """Trailing integer of the last path element, e.g. 'SimDev1/ai3' -> 3."""
    return int(re.search(r"(\d+)$", name.rsplit("/", 1)[-1]).group(1))


class SimulatedAI(AnalogInputTask):
    def __init__(self, cfg: AIConfig):
        self.cfg = cfg
        self._freqs = np.array([SIM_TONE_HZ * (_index(c.name) + 1) for c in cfg.channels])
        self._rng = np.random.default_rng(0)
        self._t0 = None
        self._n_read = 0

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._n_read = 0

    def read(self, n_samples: int, timeout: float = 10.0) -> np.ndarray:
        if self._t0 is None:
            raise BackendError("task not started")
        fs = self.cfg.sample_rate
        due = self._t0 + (self._n_read + n_samples) / fs
        wait = due - time.monotonic()
        if wait > timeout:
            raise TimeoutError("simulated read timed out")
        if wait > 0:
            time.sleep(wait)
        t = (self._n_read + np.arange(n_samples)) / fs
        data = SIM_AMPLITUDE * np.sin(2 * np.pi * self._freqs[:, None] * t[None, :])
        data += self._rng.normal(0.0, SIM_NOISE, data.shape)
        self._n_read += n_samples
        lo = np.array([c.min_val for c in self.cfg.channels])[:, None]
        hi = np.array([c.max_val for c in self.cfg.channels])[:, None]
        return np.clip(data, lo, hi)

    def stop(self) -> None:
        self._t0 = None

    def close(self) -> None:
        self.stop()


class SimulatedAO(AnalogOutputTask):
    """Records what was commanded so tests and the GUI can inspect it."""

    def __init__(self, cfg: AOConfig):
        self.cfg = cfg
        self.values = np.zeros(len(cfg.channels))
        self.waveform = None
        self.waveform_rate = None

    def _check(self, v: np.ndarray) -> None:
        for ch, x in zip(self.cfg.channels, v):
            if not ch.min_val <= x <= ch.max_val:
                raise BackendError(f"{ch.name}: {x} V outside [{ch.min_val}, {ch.max_val}]")

    def write_point(self, values: Sequence[float]) -> None:
        v = np.asarray(values, dtype=float)
        if v.shape != self.values.shape:
            raise BackendError("one value per channel is required")
        self._check(v)
        self.waveform = None
        self.values = v

    def start_waveform(self, samples: np.ndarray, sample_rate: float) -> None:
        samples = np.asarray(samples, dtype=float)
        if samples.ndim != 2 or samples.shape[0] != len(self.cfg.channels):
            raise BackendError("samples must have shape (n_channels, n_samples)")
        self._check(samples.max(axis=1))
        self._check(samples.min(axis=1))
        self.waveform = samples
        self.waveform_rate = sample_rate

    def stop(self) -> None:
        self.waveform = None

    def close(self) -> None:
        self.stop()


class SimulatedDI(DigitalInputTask):
    """Line k toggles at 1 Hz shifted by k/N of a period."""

    def __init__(self, cfg: DIOConfig):
        self.cfg = cfg
        self._idx = np.array([_index(line) for line in cfg.lines])

    def read(self) -> np.ndarray:
        phase = (time.monotonic() + self._idx / N_LINES) % 1.0
        return phase < 0.5

    def close(self) -> None:
        pass


class SimulatedDO(DigitalOutputTask):
    def __init__(self, cfg: DIOConfig):
        self.cfg = cfg
        self.values = np.zeros(len(cfg.lines), dtype=bool)

    def write(self, values: Sequence[bool]) -> None:
        v = np.asarray(values, dtype=bool)
        if v.shape != self.values.shape:
            raise BackendError("one value per line is required")
        self.values = v

    def close(self) -> None:
        pass


class SimulatedCounter(CounterInputTask):
    """Input signal is a SIM_PULSE_HZ pulse train starting at start()."""

    def __init__(self, cfg: CounterConfig):
        self.cfg = cfg
        self._t0 = None
        self._rng = np.random.default_rng(1)

    def start(self) -> None:
        self._t0 = time.monotonic()

    def read(self) -> float:
        if self._t0 is None:
            raise BackendError("task not started")
        if self.cfg.mode == "edges":
            return float(int((time.monotonic() - self._t0) * SIM_PULSE_HZ))
        return SIM_PULSE_HZ * (1.0 + self._rng.normal(0.0, 1e-4))

    def stop(self) -> None:
        self._t0 = None

    def close(self) -> None:
        self.stop()


class SimulatedBackend(Backend):
    name = "simulated"

    def list_devices(self) -> List[DeviceInfo]:
        return [DeviceInfo(
            name=DEVICE, product_type="Simulated multifunction device",
            ai_channels=[f"{DEVICE}/ai{i}" for i in range(N_AI)],
            ao_channels=[f"{DEVICE}/ao{i}" for i in range(N_AO)],
            di_lines=[f"{DEVICE}/port0/line{i}" for i in range(N_LINES)],
            do_lines=[f"{DEVICE}/port1/line{i}" for i in range(N_LINES)],
            counters=[f"{DEVICE}/ctr{i}" for i in range(N_CTR)],
            max_ai_rate=250_000.0)]

    def create_ai(self, cfg: AIConfig) -> SimulatedAI:
        cfg.validate()
        return SimulatedAI(cfg)

    def create_ao(self, cfg: AOConfig) -> SimulatedAO:
        cfg.validate()
        return SimulatedAO(cfg)

    def create_di(self, cfg: DIOConfig) -> SimulatedDI:
        cfg.validate()
        return SimulatedDI(cfg)

    def create_do(self, cfg: DIOConfig) -> SimulatedDO:
        cfg.validate()
        return SimulatedDO(cfg)

    def create_counter(self, cfg: CounterConfig) -> SimulatedCounter:
        cfg.validate()
        return SimulatedCounter(cfg)
