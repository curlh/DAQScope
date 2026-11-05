"""A minimal stand-in for the nidaqmx package so the NI backend can be tested without a driver."""
import enum
import sys
import types

import numpy as np


def install():
    """Put fake nidaqmx modules into sys.modules and return the recorder object."""
    rec = types.SimpleNamespace(tasks=[], devices=[], fail_next_read=None, closed=0)

    class DaqError(Exception):
        def __init__(self, msg, code=-1):
            super().__init__(msg)
            self.error_code = code

    def enum_of(name, *members):
        return enum.Enum(name, {m: i for i, m in enumerate(members)})

    constants = types.ModuleType("nidaqmx.constants")
    constants.AcquisitionType = enum_of("AcquisitionType", "FINITE", "CONTINUOUS")
    constants.TerminalConfiguration = enum_of("TerminalConfiguration", "DEFAULT", "RSE", "NRSE", "DIFF", "PSEUDO_DIFF")
    constants.Edge = enum_of("Edge", "RISING", "FALLING")
    constants.CountDirection = enum_of("CountDirection", "COUNT_UP")
    constants.FrequencyUnits = enum_of("FrequencyUnits", "HZ")
    constants.LineGrouping = enum_of("LineGrouping", "CHAN_FOR_ALL_LINES", "CHAN_PER_LINE")

    class Collection:
        def __init__(self, task, kind):
            self.task, self.kind = task, kind

        def __getattr__(self, name):
            if name.startswith("add_"):
                def add(*args, **kw):
                    self.task.channels.append((name, args, kw))
                return add
            raise AttributeError(name)

    class Timing:
        def __init__(self, task):
            self.task = task

        def cfg_samp_clk_timing(self, rate, **kw):
            self.task.timing = (rate, kw)

    class Task:
        def __init__(self):
            self.channels, self.timing_cfg, self.writes, self.started, self.stopped, self.closed = [], None, [], 0, 0, False
            self.ai_channels = Collection(self, "ai")
            self.ao_channels = Collection(self, "ao")
            self.di_channels = Collection(self, "di")
            self.do_channels = Collection(self, "do")
            self.ci_channels = Collection(self, "ci")
            self.timing_obj = Timing(self)
            self.in_stream = object()
            self.read_value = None
            rec.tasks.append(self)

        @property
        def timing(self):
            return self.timing_obj

        @timing.setter
        def timing(self, value):
            self.timing_cfg = value

        def start(self):
            self.started += 1

        def stop(self):
            self.stopped += 1

        def close(self):
            self.closed = True
            rec.closed += 1

        def write(self, data, auto_start=None, timeout=10.0):
            self.writes.append((data, auto_start))

        def read(self):
            return self.read_value

    readers = types.ModuleType("nidaqmx.stream_readers")

    class AnalogMultiChannelReader:
        def __init__(self, stream):
            pass

        def read_many_sample(self, data, number_of_samples_per_channel=-1, timeout=10.0):
            if rec.fail_next_read is not None:
                err, rec.fail_next_read = rec.fail_next_read, None
                raise err
            data[:] = np.arange(data.shape[1])[None, :] + np.arange(data.shape[0])[:, None] * 100
            return data.shape[1]

    readers.AnalogMultiChannelReader = AnalogMultiChannelReader

    class Chans:
        def __init__(self, names):
            self.channel_names = names

    class Device:
        def __init__(self, name, product, **kw):
            self.name, self.product_type = name, product
            self.ai_physical_chans = Chans(kw.get("ai", []))
            self.ao_physical_chans = Chans(kw.get("ao", []))
            self.di_lines = Chans(kw.get("di", []))
            self.do_lines = Chans(kw.get("do", []))
            self.ci_physical_chans = Chans(kw.get("ci", []))
            self.ai_max_multi_chan_rate = kw.get("rate", 250000.0)

    class System:
        @staticmethod
        def local():
            return types.SimpleNamespace(devices=rec.devices)

    system = types.ModuleType("nidaqmx.system")
    system.System = System
    errors = types.ModuleType("nidaqmx.errors")
    errors.DaqError = DaqError
    errors.Error = DaqError
    top = types.ModuleType("nidaqmx")
    top.Task = Task
    top.constants, top.stream_readers, top.system, top.errors = constants, readers, system, errors
    for name, mod in {"nidaqmx": top, "nidaqmx.constants": constants, "nidaqmx.stream_readers": readers,
                      "nidaqmx.system": system, "nidaqmx.errors": errors}.items():
        sys.modules[name] = mod
    rec.Device, rec.DaqError = Device, DaqError
    return rec


def uninstall():
    for name in [n for n in sys.modules if n == "nidaqmx" or n.startswith("nidaqmx.")]:
        del sys.modules[name]
    sys.modules.pop("daqscope.backends.nidaqmx_backend", None)
