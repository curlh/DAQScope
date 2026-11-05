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
from .trigger import auto_hysteresis, find_edges

DIVS_X = 10
DIVS_Y = 8
ROLL_TDIV = 0.1          # s/div at and above which auto mode rolls instead of triggering


@dataclass
class TriggerConfig:
    source: int = 0              # channel index
    level: float = 0.0           # volts
    slope: str = "rising"        # "rising" or "falling"
    mode: str = "auto"           # "auto", "normal" or "single"
    hysteresis: Optional[float] = None   # volts, None picks it from the noise on the source


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
        self.hysteresis_used = 0.0   # hysteresis applied by the last search, volts
        self._consumed = 0           # samples before this index belong to frames already shown
        self._scan_from = 0          # samples before this index were already searched for an edge
        self._carry = 0              # trigger arming state at the end of the last search
        self._sig = None             # trigger settings the carried state belongs to
        self._wait_start = 0.0

    @property
    def span(self) -> int:
        return max(2, int(round(DIVS_X * self.time_per_div * self.sample_rate)))

    def max_time_per_div(self, buffer: RingBuffer) -> float:
        """Slowest timebase whose screen fits the buffer with room to find a trigger."""
        return buffer.capacity / 2 / self.sample_rate / DIVS_X

    def run(self, buffer: RingBuffer, now: Optional[float] = None) -> None:
        self._consumed = self._scan_from = buffer.total_written
        self._carry = 0
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
        lo = max(self._scan_from, base + pre + 1)
        hi = total - post                      # last usable trigger sample
        if hi > lo:
            start = lo - 1
            origin = start - pre               # absolute index of seg[:, 0]
            snap = buffer.window(origin)
            if snap is None:
                return None
            seg = snap[0]
            src = seg[trig.source]
            hyst = trig.hysteresis
            if hyst is None:
                # With zero hysteresis, noise on a slow edge makes the trigger fire on the
                # opposite slope too, so the picture jumped between phases from frame to frame.
                hyst = auto_hysteresis(src[-20000:])
            self.hysteresis_used = hyst
            sig = (trig.source, trig.level, trig.slope, trig.hysteresis)
            if sig != self._sig:
                self._sig, self._carry = sig, 0
            # The search resumes on the last sample of the previous one and keeps the arming
            # state. Without it an edge was missed whenever the part of the slope below the
            # hysteresis band had been seen in an earlier search (slow signal, fast timebase).
            edges, carry = find_edges(src[pre:pre + (hi - start) + 1], trig.level, trig.slope,
                                      hyst, self._carry, return_state=True)
            if edges.size:
                self._carry = 0
                pos = start + edges[-1]        # absolute fractional trigger position
                ti = int(np.floor(pos))
                a = ti - pre - origin
                frame = ScopeFrame(seg[:, a:a + span].copy(), self.sample_rate, pre,
                                   pos - ti, True, False)
                self._consumed = self._scan_from = ti + post
                self._wait_start = now
                if trig.mode == "single":
                    self.stop()
                    self.status = "Stop"
                else:
                    self.status = "Trig'd"
                return frame
            # nothing in [lo, hi]; the next search starts where this one ended, so every
            # sample is searched once no matter how many arrive between two updates
            self._scan_from = hi + 1
            self._carry = carry

        waited = now - self._wait_start > span / self.sample_rate + 0.25
        if trig.mode == "auto" and waited:
            self._wait_start = now
            self._consumed = self._scan_from = total
            self._carry = 0
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
