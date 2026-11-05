from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class Recording:
    data: np.ndarray            # (n_channels, n_samples)
    channels: List[str]
    sample_rate: float
    start_time: str

    @property
    def time(self) -> np.ndarray:
        return np.arange(self.data.shape[1]) / self.sample_rate


def read_recording(path: str) -> Recording:
    ext = str(path).rsplit(".", 1)[-1].lower()
    if ext == "npz":
        with np.load(path) as z:
            return Recording(z["data"], [str(c) for c in z["channels"]],
                             float(z["sample_rate"]), str(z["start_time"]))
    if ext in ("h5", "hdf5"):
        import h5py
        with h5py.File(path, "r") as f:
            chans = [c.decode() if isinstance(c, bytes) else str(c) for c in f.attrs["channels"]]
            return Recording(f["data"][...], chans, float(f.attrs["sample_rate"]),
                             str(f.attrs["start_time"]))
    if ext == "csv":
        meta = {}
        with open(path) as f:
            line = f.readline()
            while line.startswith("#"):
                k, v = line[1:].strip().split("=", 1)
                meta[k] = v
                line = f.readline()
            header = line.strip().split(",")
            rows = np.loadtxt(f, delimiter=",", ndmin=2)
        return Recording(rows[:, 1:].T.copy(), header[1:], float(meta["sample_rate"]),
                         meta.get("start_time", ""))
    raise ValueError(f"unsupported file type {ext!r}")
