"""Background file writers. put() only enqueues, so the acquisition thread never waits on disk."""
from __future__ import annotations

import datetime as _dt
import queue
import threading
from typing import Optional, Sequence

import numpy as np

_STOP = object()


class BlockWriter:
    """Base class: a worker thread drains a queue of (n_channels, n) blocks."""

    def __init__(self, path: str, channels: Sequence[str], sample_rate: float):
        self.path = str(path)
        self.channels = list(channels)
        self.sample_rate = float(sample_rate)
        self.start_time = _dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        self.samples_written = 0
        self.error: Optional[BaseException] = None
        self._q: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="daqscope-writer", daemon=True)
        self._open()
        self._thread.start()

    def put(self, block: np.ndarray) -> None:
        self._q.put(np.array(block, copy=True))

    def close(self) -> None:
        self._q.put(_STOP)
        self._thread.join()
        if self.error is not None:
            raise self.error

    def __enter__(self) -> "BlockWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _run(self) -> None:
        try:
            while True:
                item = self._q.get()
                if item is _STOP:
                    break
                self._write(item)
                self.samples_written += item.shape[1]
        except BaseException as exc:
            self.error = exc
        finally:
            try:
                self._finish()
            except BaseException as exc:
                self.error = self.error or exc

    def _open(self) -> None: ...
    def _write(self, block: np.ndarray) -> None: ...
    def _finish(self) -> None: ...


class NpzWriter(BlockWriter):
    """Keeps blocks in memory and saves once on close. Use HDF5 or CSV for long runs."""

    def _open(self) -> None:
        self._blocks = []

    def _write(self, block: np.ndarray) -> None:
        self._blocks.append(block)

    def _finish(self) -> None:
        data = np.concatenate(self._blocks, axis=1) if self._blocks else np.zeros((len(self.channels), 0))
        np.savez(self.path, data=data, channels=np.array(self.channels),
                 sample_rate=self.sample_rate, start_time=self.start_time)


class Hdf5Writer(BlockWriter):
    def _open(self) -> None:
        import h5py
        n = len(self.channels)
        self._f = h5py.File(self.path, "w")
        self._ds = self._f.create_dataset("data", shape=(n, 0), maxshape=(n, None),
                                          dtype="f8", chunks=(n, 4096))
        self._f.attrs["channels"] = np.array(self.channels, dtype="S")
        self._f.attrs["sample_rate"] = self.sample_rate
        self._f.attrs["start_time"] = self.start_time

    def _write(self, block: np.ndarray) -> None:
        n0 = self._ds.shape[1]
        self._ds.resize(n0 + block.shape[1], axis=1)
        self._ds[:, n0:] = block

    def _finish(self) -> None:
        self._f.close()


class CsvWriter(BlockWriter):
    def _open(self) -> None:
        self._f = open(self.path, "w", newline="")
        self._f.write(f"# sample_rate={self.sample_rate!r}\n# start_time={self.start_time}\n")
        self._f.write("time_s," + ",".join(self.channels) + "\n")

    def _write(self, block: np.ndarray) -> None:
        t = (self.samples_written + np.arange(block.shape[1])) / self.sample_rate
        rows = np.column_stack([t, block.T])
        np.savetxt(self._f, rows, delimiter=",", fmt="%.9g")

    def _finish(self) -> None:
        self._f.close()


_WRITERS = {"npz": NpzWriter, "h5": Hdf5Writer, "hdf5": Hdf5Writer, "csv": CsvWriter}


def open_writer(path: str, channels: Sequence[str], sample_rate: float, fmt: Optional[str] = None) -> BlockWriter:
    """Create a writer, choosing the format from fmt or the file extension."""
    fmt = (fmt or str(path).rsplit(".", 1)[-1]).lower()
    if fmt not in _WRITERS:
        raise ValueError(f"unsupported format {fmt!r}, use one of {sorted(_WRITERS)}")
    return _WRITERS[fmt](path, channels, sample_rate)
