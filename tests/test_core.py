import time

import numpy as np
import pytest

from daqscope.backends import get_backend
from daqscope.core import (AIChannel, AIConfig, AOChannel, AOConfig, AcquisitionSession,
                           ConfigError, CounterConfig, DIOConfig, RingBuffer, Scale,
                           StreamRunner, one_period)
from daqscope.core.errors import BackendError


def ai_cfg(n=2, fs=10_000):
    return AIConfig([AIChannel(f"SimDev1/ai{i}") for i in range(n)], sample_rate=fs)


def test_device_listing():
    dev = get_backend("simulated").list_devices()[0]
    assert dev.name == "SimDev1" and len(dev.ai_channels) == 8 and len(dev.counters) == 2


def test_read_shape_and_tone():
    with AcquisitionSession(get_backend(), ai_cfg(fs=10_000)) as s:
        d = s.read(10_000)
    assert d.shape == (2, 10_000)
    spec = np.abs(np.fft.rfft(d[0]))
    assert int(np.argmax(spec)) == 10          # ai0 tone at 10 Hz over 1 s


def test_read_is_paced_in_real_time():
    t0 = time.monotonic()
    with AcquisitionSession(get_backend(), ai_cfg(fs=2000)) as s:
        s.read(1000)
    assert time.monotonic() - t0 >= 0.45


def test_scaling_applied():
    cfg = AIConfig([AIChannel("SimDev1/ai0", scale=Scale(gain=2.0, offset=1.0, unit="A"))], 5000)
    with AcquisitionSession(get_backend(), cfg) as s:
        d = s.read(5000)
    assert d.mean() == pytest.approx(1.0, abs=0.05)
    assert d.max() > 2.5


def test_invalid_config():
    with pytest.raises(ConfigError):
        AIConfig([], 1000).validate()
    with pytest.raises(ConfigError):
        AIConfig([AIChannel("x", min_val=1, max_val=0)], 1000).validate()


def test_ring_buffer_wraps():
    rb = RingBuffer(1, 10)
    rb.write(np.arange(7)[None, :].astype(float))
    rb.write(np.arange(7, 14)[None, :].astype(float))
    assert rb.latest(5)[0].tolist() == [9, 10, 11, 12, 13]
    assert rb.total_written == 14
    assert rb.latest(100).shape[1] == 10


def test_stream_runner_fills_buffer_and_notifies():
    got = []
    with AcquisitionSession(get_backend(), ai_cfg(fs=5000)) as s:
        r = StreamRunner(s, block_seconds=0.05)
        r.subscribe(lambda b: got.append(b.shape[1]))
        r.start()
        time.sleep(0.5)
        r.stop()
    assert r.error is None
    assert r.buffer.total_written == sum(got) and sum(got) >= 2000


def test_waveforms():
    y, f = one_period("sine", 100, 10_000, amplitude=2, offset=1)
    assert len(y) == 100 and f == 100 and y.max() == pytest.approx(3, abs=1e-2)
    y, _ = one_period("square", 100, 10_000)
    assert set(np.unique(y)) == {-1.0, 1.0}
    y, _ = one_period("triangle", 100, 10_000)
    assert y.max() == pytest.approx(1.0, abs=0.05) and y.min() == pytest.approx(-1.0, abs=0.05)
    assert abs(y.mean()) < 1e-9
    with pytest.raises(ConfigError):
        one_period("sine", 6000, 10_000)


def test_analog_output():
    ao = get_backend().create_ao(AOConfig([AOChannel("SimDev1/ao0", -5, 5)]))
    ao.write_point([2.5])
    assert ao.values[0] == 2.5
    with pytest.raises(BackendError):
        ao.write_point([6.0])
    y, _ = one_period("sine", 100, 10_000, amplitude=1)
    ao.start_waveform(y[None, :], 10_000)
    assert ao.waveform.shape == (1, 100)
    ao.stop()
    assert ao.waveform is None


def test_digital_io():
    b = get_backend()
    di = b.create_di(DIOConfig([f"SimDev1/port0/line{i}" for i in range(4)]))
    assert di.read().dtype == bool and di.read().shape == (4,)
    do = b.create_do(DIOConfig(["SimDev1/port1/line0", "SimDev1/port1/line1"]))
    do.write([True, False])
    assert do.values.tolist() == [True, False]


def test_counter():
    b = get_backend()
    c = b.create_counter(CounterConfig("SimDev1/ctr0", mode="edges"))
    c.start()
    time.sleep(0.2)
    assert 100 < c.read() < 400
    f = b.create_counter(CounterConfig("SimDev1/ctr1", mode="frequency"))
    f.start()
    assert f.read() == pytest.approx(1000.0, rel=1e-2)
