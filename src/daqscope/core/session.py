from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable, List, Optional

import numpy as np

from .buffer import RingBuffer
from .config import AIConfig
from .scaling import apply_scales

if TYPE_CHECKING:   # core must not import backends at runtime (backends import core)
    from ..backends.base import Backend


class AcquisitionSession:
    """Pull-style analog input: start(), read(n) returns scaled numpy data, stop()."""

    def __init__(self, backend: "Backend", cfg: AIConfig):
        cfg.validate()
        self.cfg = cfg
        self._task = backend.create_ai(cfg)
        self._running = False

    def start(self) -> None:
        self._task.start()
        self._running = True

    def read(self, n_samples: int, timeout: float = 10.0) -> np.ndarray:
        """Next n_samples as (n_channels, n_samples) with channel scales applied."""
        if not self._running:
            self.start()
        return apply_scales(self._task.read(n_samples, timeout), self.cfg.channels)

    def stop(self) -> None:
        if self._running:
            self._task.stop()
            self._running = False

    def close(self) -> None:
        self.stop()
        self._task.close()

    def __enter__(self) -> "AcquisitionSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class StreamRunner:
    """Reads blocks on a worker thread, fills a ring buffer and notifies subscribers.

    Subscribers run on the worker thread and must return quickly; writers and GUI
    bridges should only enqueue the block.
    """

    def __init__(self, session: AcquisitionSession, block_seconds: float = 0.05,
                 buffer_seconds: float = 10.0):
        fs = session.cfg.sample_rate
        self.session = session
        self.block_size = max(1, int(fs * block_seconds))
        self.buffer = RingBuffer(session.cfg.n_channels, max(self.block_size, int(fs * buffer_seconds)))
        self.error: Optional[BaseException] = None
        self._subs: List[Callable[[np.ndarray], None]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def subscribe(self, callback: Callable[[np.ndarray], None]) -> None:
        self._subs.append(callback)

    def unsubscribe(self, callback: Callable[[np.ndarray], None]) -> None:
        if callback in self._subs:
            self._subs.remove(callback)

    def start(self) -> None:
        self.error = None
        self._stop.clear()
        self.session.start()
        self._thread = threading.Thread(target=self._run, name="daqscope-stream", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    block = self.session.read(self.block_size, timeout=0.5)
                except TimeoutError:
                    continue
                self.buffer.write(block)
                for cb in list(self._subs):
                    cb(block)
        except BaseException as exc:   # surfaced to the owner through .error
            self.error = exc

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self.session.stop()
