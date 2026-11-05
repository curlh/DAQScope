"""Oscilloscope display engine: timebase, edge trigger and run/stop logic.

The engine only reads from a RingBuffer, so it has no Qt or hardware dependency. A GUI calls
update() from a timer and draws the returned frame, one frame per trigger event.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .buffer import RingBuffer
from .trigger import find_edges

DIVS_X = 10
DIVS_Y = 8
ROLL_TDIV = 0.1          # s/div at and above which auto mode rolls instead of triggering


@dataclass
class TriggerConfig:
    source: int = 0              # channel index
    level: float = 0.0           # volts
    slope: str = "rising"        # "rising" or "falling"
    mode: str = "auto"           # "auto", "normal" or "single"
    hysteresis: float = 0.0      # volts


@dataclass
class ScopeFrame:
    data: np.ndarray             # (n_channels, span); NaN where no data exists yet
    sample_rate: float
    pre: int                     # samples left of the trigger point
    frac: float                  # sub-sample offset of the trigger point
    triggered: bool
    rolling: bool

    @property
    def time(self) -> np.ndarray:
        """Seconds relative to the trigger point (screen centre by default)."""
        return (np.arange(self.data.shape[1]) - self.pre - self.frac) / self.sample_rate

    @property
    def valid_from(self) -> int:
        bad = np.nonzero(np.isnan(self.data[0]))[0]
        return int(bad[-1]) + 1 if bad.size else 0


class ScopeEngine:
    def __init__(self, sample_rate: float, n_channels: int):
        self.sample_rate = float(sample_rate)
        self.n_channels = n_channels
        self.time_per_div = 1e-3
        self.trigger_pos = 0.5       # fraction of the screen left of the trigger point
        self.trigger = TriggerConfig()
        self.running = False
        self.status = "Stop"
        self._consumed = 0
        self._wait_start = 0.0

    @property
    def span(self) -> int:
        return max(2, int(round(DIVS_X * self.time_per_div * self.sample_rate)))

    def max_time_per_div(self, buffer: RingBuffer) -> float:
        """Slowest timebase whose screen fits the buffer with room to find a trigger."""
        return buffer.capacity / 2 / self.sample_rate / DIVS_X

    def run(self, buffer: RingBuffer, now: Optional[float] = None) -> None:
        self._consumed = buffer.total_written
        self._wait_start = time.monotonic() if now is None else now
        self.running = True
        self.status = "Armed"

    def stop(self) -> None:
        self.running = False
        self.status = "Stop"

    def update(self, buffer: RingBuffer, now: Optional[float] = None) -> Optional[ScopeFrame]:
        """Return a new frame if one is ready, else None (keep showing the previous one)."""
        if not self.running:
            return None
        now = time.monotonic() if now is None else now
        trig = self.trigger
        span = self.span
        pre = int(round(span * self.trigger_pos))
        post = span - pre
        total = buffer.total_written
        if span > buffer.capacity // 2:
            self.status = "Timebase too slow"
            return None

        if trig.mode == "auto" and self.time_per_div >= ROLL_TDIV:
            self.status = "Roll"
            return self._latest(buffer, span, pre)

        base = total - min(total, buffer.capacity)
        lo = max(self._consumed, base + pre + 1)
        hi = total - post                      # last usable trigger sample
        # only the newest 4 screens are searched, so the display never lags behind the input
        lo = max(lo, hi - 4 * span)
        if hi > lo:
            start = lo - 1
            origin = start - pre               # absolute index of seg[:, 0]
            snap = buffer.window(origin)
            if snap is None:
                return None
            seg = snap[0]
            edges = find_edges(seg[trig.source, pre:pre + (hi - start) + 1], trig.level,
                               trig.slope, trig.hysteresis)
            if edges.size:
                pos = start + edges[-1]        # absolute fractional trigger position
                ti = int(np.floor(pos))
                a = ti - pre - origin
                frame = ScopeFrame(seg[:, a:a + span].copy(), self.sample_rate, pre,
                                   pos - ti, True, False)
                self._consumed = ti + post
                self._wait_start = now
                if trig.mode == "single":
                    self.stop()
                    self.status = "Stop"
                else:
                    self.status = "Trig'd"
                return frame

        waited = now - self._wait_start > span / self.sample_rate + 0.1
        if trig.mode == "auto" and waited:
            self._wait_start = now
            self._consumed = total
            self.status = "Auto"
            return self._latest(buffer, span, pre, triggered=False)
        if waited and trig.mode != "auto":
            self.status = "Ready"          # armed, no trigger for longer than one screen
        return None

    def _latest(self, buffer: RingBuffer, span: int, pre: int, triggered: bool = False) -> ScopeFrame:
        data = buffer.latest(span)
        if data.shape[1] < span:
            pad = np.full((data.shape[0], span - data.shape[1]), np.nan)
            data = np.concatenate([pad, data], axis=1)
        return ScopeFrame(data, self.sample_rate, pre, 0.0, triggered, not triggered and self.status == "Roll")
