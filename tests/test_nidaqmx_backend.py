import importlib

import numpy as np
import pytest

import fake_nidaqmx
from daqscope.core import (AIChannel, AIConfig, AOChannel, AOConfig, CounterConfig, DIOConfig)
from daqscope.core.errors import BackendError


@pytest.fixture
def ni():
    rec = fake_nidaqmx.install()
    mod = importlib.import_module("daqscope.backends.nidaqmx_backend")
    yield rec, mod
    fake_nidaqmx.uninstall()


def test_device_listing(ni):
    rec, mod = ni
    rec.devices.append(rec.Device("Dev1", "PCIe-6321", ai=["Dev1/ai0", "Dev1/ai1"], ao=["Dev1/ao0"],
                                  di=["Dev1/port0/line0"], do=["Dev1/port0/line1"], ci=["Dev1/ctr0"]))
    (d,) = mod.NidaqmxBackend().list_devices()
    assert d.name == "Dev1" and d.product_type == "PCIe-6321" and d.ai_channels == ["Dev1/ai0", "Dev1/ai1"]
    assert d.counters == ["Dev1/ctr0"] and d.max_ai_rate == 250000.0


def test_analog_input_setup_and_read(ni):
    rec, mod = ni
    cfg = AIConfig([AIChannel("Dev1/ai0", terminal="RSE", min_val=-5, max_val=5), AIChannel("Dev1/ai1")], 100_000)
    ai = mod.NidaqmxBackend().create_ai(cfg)
    task = rec.tasks[-1]
    assert [c[1][0] for c in task.channels] == ["Dev1/ai0", "Dev1/ai1"]
    assert task.channels[0][2]["min_val"] == -5 and task.channels[0][2]["terminal_config"].name == "RSE"
    rate, kw = task.timing_cfg
    assert rate == 100_000 and kw["sample_mode"].name == "CONTINUOUS" and kw["samps_per_chan"] == 200_000
    ai.start()
    data = ai.read(5)
    assert data.shape == (2, 5) and data[1, 0] == 100
    ai.stop()
    ai.close()
    assert task.started == 1 and task.stopped == 1 and task.closed


def test_read_timeout_is_a_timeout_error(ni):
    rec, mod = ni
    ai = mod.NidaqmxBackend().create_ai(AIConfig([AIChannel("Dev1/ai0")], 1000))
    rec.fail_next_read = rec.DaqError("not yet", -200284)
    with pytest.raises(TimeoutError):
        ai.read(10)
    rec.fail_next_read = rec.DaqError("other", -200001)
    with pytest.raises(BackendError):
        ai.read(10)


def test_driver_error_on_setup_closes_task(ni):
    rec, mod = ni
    # a channel with no valid terminal config reaches the driver as a KeyError in our mapping,
    # so provoke a driver-side error through the fake instead
    boom = rec.DaqError("bad channel")

    def fail(*a, **k):
        raise boom
    orig = mod.nidaqmx.Task

    class Bad(orig):
        def __init__(self):
            super().__init__()
            self.ai_channels.add_ai_voltage_chan = fail
    mod.nidaqmx.Task = Bad
    with pytest.raises(BackendError):
        mod.NidaqmxBackend().create_ai(AIConfig([AIChannel("Dev1/ai0")], 1000))
    assert rec.tasks[-1].closed
    mod.nidaqmx.Task = orig


def test_analog_output_point_and_waveform(ni):
    rec, mod = ni
    ao = mod.NidaqmxBackend().create_ao(AOConfig([AOChannel("Dev1/ao0"), AOChannel("Dev1/ao1")]))
    ao.write_point([1.0, 2.0])
    t1 = rec.tasks[-1]
    assert t1.writes == [([1.0, 2.0], True)]
    wave = np.vstack([np.sin(np.linspace(0, 6.28, 50)), np.zeros(50)])
    ao.start_waveform(wave, 10_000)
    t2 = rec.tasks[-1]
    assert t2 is not t1 and t1.closed                   # mode change rebuilt the task
    rate, kw = t2.timing_cfg
    assert rate == 10_000 and kw["samps_per_chan"] == 50 and t2.started == 1
    assert t2.writes[0][1] is False and t2.writes[0][0].shape == (2, 50)
    ao.stop()
    assert t2.stopped == 1
    ao.write_point([0.0, 0.0])                          # back to static output on a fresh task
    assert rec.tasks[-1] is not t2
    with pytest.raises(BackendError):
        ao.write_point([1.0])


def test_single_channel_waveform_is_one_dimensional(ni):
    rec, mod = ni
    ao = mod.NidaqmxBackend().create_ao(AOConfig([AOChannel("Dev1/ao0")]))
    ao.start_waveform(np.zeros((1, 20)), 1000)
    assert rec.tasks[-1].writes[0][0].shape == (20,)


def test_digital_io_uses_one_channel_per_line(ni):
    rec, mod = ni
    lines = ["Dev1/port0/line0", "Dev1/port0/line1"]
    b = mod.NidaqmxBackend()
    di = b.create_di(DIOConfig(lines))
    t = rec.tasks[-1]
    name, args, kw = t.channels[0]
    assert args[0] == ",".join(lines) and kw["line_grouping"].name == "CHAN_PER_LINE"
    t.read_value = [True, False]
    assert di.read().tolist() == [True, False]
    t.read_value = True
    assert di.read().tolist() == [True]
    do = b.create_do(DIOConfig(lines))
    do.write([True, False])
    assert rec.tasks[-1].writes == [([True, False], True)]


def test_counters(ni):
    rec, mod = ni
    b = mod.NidaqmxBackend()
    c = b.create_counter(CounterConfig("Dev1/ctr0", mode="edges", edge="falling"))
    t = rec.tasks[-1]
    assert t.channels[0][0] == "add_ci_count_edges_chan" and t.channels[0][2]["edge"].name == "FALLING"
    t.read_value = 42
    c.start()
    assert c.read() == 42.0
    f = b.create_counter(CounterConfig("Dev1/ctr1", mode="frequency", min_freq=10, max_freq=1e5))
    t = rec.tasks[-1]
    assert t.channels[0][0] == "add_ci_freq_chan" and t.channels[0][2]["min_val"] == 10
    f.close()
    assert t.closed
