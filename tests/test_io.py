import numpy as np
import pytest

from daqscope.io import open_writer, read_recording

CH = ["SimDev1/ai0", "SimDev1/ai1"]


def blocks():
    rng = np.random.default_rng(3)
    return [rng.normal(size=(2, n)) for n in (100, 250, 7)]


@pytest.mark.parametrize("ext", ["npz", "csv"])
def test_roundtrip(tmp_path, ext):
    path = str(tmp_path / f"rec.{ext}")
    bl = blocks()
    with open_writer(path, CH, 5000.0) as w:
        for b in bl:
            w.put(b)
    rec = read_recording(path)
    assert rec.channels == CH and rec.sample_rate == 5000.0
    tol = 1e-5 if ext == "csv" else 0
    np.testing.assert_allclose(rec.data, np.concatenate(bl, axis=1), atol=tol)
    assert rec.time[1] == pytest.approx(1 / 5000.0)
    assert rec.start_time


def test_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        open_writer(str(tmp_path / "x.bin"), CH, 1000.0)
