"""NI-DAQmx backend. This is the only module that imports nidaqmx.

Needs the NI-DAQmx driver and the nidaqmx Python package (pip install daqscope[ni]).
Written against nidaqmx 1.x.
"""
from __future__ import annotations

from typing import List, Sequence

import numpy as np
import nidaqmx
from nidaqmx.constants import (AcquisitionType, CountDirection, Edge, FrequencyUnits,
                               LineGrouping, TerminalConfiguration)
from nidaqmx.errors import DaqError, Error
from nidaqmx.stream_readers import AnalogMultiChannelReader
from nidaqmx.system import System

from ..core.config import (AIConfig, AOConfig, CounterConfig, DeviceInfo,
                           DIOConfig)
from ..core.errors import BackendError
from .base import (AnalogInputTask, AnalogOutputTask, Backend,
                   CounterInputTask, DigitalInputTask, DigitalOutputTask)

SAMPLES_NOT_YET_AVAILABLE = -200284     # read timed out before n samples arrived

_TERMINALS = {
    "DEFAULT": TerminalConfiguration.DEFAULT,
    "RSE": TerminalConfiguration.RSE,
    "NRSE": TerminalConfiguration.NRSE,
    "DIFF": TerminalConfiguration.DIFF,
    "PSEUDO_DIFF": TerminalConfiguration.PSEUDO_DIFF,
}


def _wrap(exc: DaqError) -> BackendError:
    return BackendError(f"NI-DAQmx: {exc}")


class _Closing:
    """Mixin that closes a nidaqmx task and reports driver errors as BackendError."""
    _task = None

    def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            try:
                task.close()
            except DaqError as exc:
                raise _wrap(exc)


class NidaqmxAI(_Closing, AnalogInputTask):
    def __init__(self, cfg: AIConfig):
        self.cfg = cfg
        self._reader = None
        try:
            self._task = nidaqmx.Task()
            for ch in cfg.channels:
                self._task.ai_channels.add_ai_voltage_chan(
                    ch.name, terminal_config=_TERMINALS[ch.terminal],
                    min_val=ch.min_val, max_val=ch.max_val)
            # two seconds of driver buffer, so a slow GUI refresh does not overrun the card
            self._task.timing.cfg_samp_clk_timing(
                cfg.sample_rate, sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=int(max(2 * cfg.sample_rate, 10_000)))
            self._reader = AnalogMultiChannelReader(self._task.in_stream)
        except DaqError as exc:
            self.close()
            raise _wrap(exc)

    def start(self) -> None:
        try:
            self._task.start()
        except DaqError as exc:
            raise _wrap(exc)

    def read(self, n_samples: int, timeout: float = 10.0) -> np.ndarray:
        data = np.empty((len(self.cfg.channels), n_samples))
        try:
            self._reader.read_many_sample(data, number_of_samples_per_channel=n_samples,
                                          timeout=timeout)
        except DaqError as exc:
            if exc.error_code == SAMPLES_NOT_YET_AVAILABLE:
                raise TimeoutError("samples did not arrive within the timeout") from exc
            raise _wrap(exc)
        return data

    def stop(self) -> None:
        try:
            if self._task is not None:
                self._task.stop()
        except DaqError as exc:
            raise _wrap(exc)


class NidaqmxAO(_Closing, AnalogOutputTask):
    """A static value or a regenerated waveform. A mode change rebuilds the task."""

    def __init__(self, cfg: AOConfig):
        self.cfg = cfg
        self._mode = None
        self._new_task()

    def _new_task(self) -> None:
        self.close()
        try:
            self._task = nidaqmx.Task()
            for ch in self.cfg.channels:
                self._task.ao_channels.add_ao_voltage_chan(ch.name, min_val=ch.min_val,
                                                           max_val=ch.max_val)
        except DaqError as exc:
            self.close()
            raise _wrap(exc)
        self._mode = None

    def write_point(self, values: Sequence[float]) -> None:
        v = np.asarray(values, dtype=float)
        if v.shape != (len(self.cfg.channels),):
            raise BackendError("one value per channel is required")
        try:
            if self._mode != "static":
                self._new_task()
                self._mode = "static"
            self._task.write(float(v[0]) if v.size == 1 else v.tolist(), auto_start=True)
        except DaqError as exc:
            raise _wrap(exc)

    def start_waveform(self, samples: np.ndarray, sample_rate: float) -> None:
        samples = np.asarray(samples, dtype=float)
        if samples.ndim != 2 or samples.shape[0] != len(self.cfg.channels):
            raise BackendError("samples must have shape (n_channels, n_samples)")
        try:
            self._new_task()
            self._task.timing.cfg_samp_clk_timing(
                sample_rate, sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=samples.shape[1])
            # the driver regenerates the buffer by default in continuous mode
            self._task.write(samples[0] if samples.shape[0] == 1 else samples, auto_start=False)
            self._task.start()
            self._mode = "waveform"
        except DaqError as exc:
            raise _wrap(exc)

    def stop(self) -> None:
        if self._mode == "waveform":
            try:
                self._task.stop()
            except DaqError as exc:
                raise _wrap(exc)
            self._mode = None


class NidaqmxDI(_Closing, DigitalInputTask):
    def __init__(self, cfg: DIOConfig):
        try:
            self._task = nidaqmx.Task()
            # one channel per line, otherwise read() returns the lines packed into one integer
            self._task.di_channels.add_di_chan(",".join(cfg.lines),
                                               line_grouping=LineGrouping.CHAN_PER_LINE)
        except DaqError as exc:
            self.close()
            raise _wrap(exc)

    def read(self) -> np.ndarray:
        try:
            return np.atleast_1d(np.asarray(self._task.read(), dtype=bool))
        except DaqError as exc:
            raise _wrap(exc)


class NidaqmxDO(_Closing, DigitalOutputTask):
    def __init__(self, cfg: DIOConfig):
        self._n = len(cfg.lines)
        try:
            self._task = nidaqmx.Task()
            self._task.do_channels.add_do_chan(",".join(cfg.lines),
                                               line_grouping=LineGrouping.CHAN_PER_LINE)
        except DaqError as exc:
            self.close()
            raise _wrap(exc)

    def write(self, values: Sequence[bool]) -> None:
        v = np.asarray(values, dtype=bool)
        if v.shape != (self._n,):
            raise BackendError("one value per line is required")
        try:
            self._task.write(bool(v[0]) if v.size == 1 else v.tolist(), auto_start=True)
        except DaqError as exc:
            raise _wrap(exc)


class NidaqmxCounter(_Closing, CounterInputTask):
    def __init__(self, cfg: CounterConfig):
        self.cfg = cfg
        edge = Edge.RISING if cfg.edge == "rising" else Edge.FALLING
        try:
            self._task = nidaqmx.Task()
            if cfg.mode == "edges":
                self._task.ci_channels.add_ci_count_edges_chan(
                    cfg.channel, edge=edge, initial_count=0,
                    count_direction=CountDirection.COUNT_UP)
            else:
                self._task.ci_channels.add_ci_freq_chan(
                    cfg.channel, min_val=cfg.min_freq, max_val=cfg.max_freq,
                    units=FrequencyUnits.HZ, edge=edge)
        except DaqError as exc:
            self.close()
            raise _wrap(exc)

    def start(self) -> None:
        try:
            self._task.start()
        except DaqError as exc:
            raise _wrap(exc)

    def read(self) -> float:
        try:
            return float(self._task.read())
        except DaqError as exc:
            raise _wrap(exc)

    def stop(self) -> None:
        try:
            if self._task is not None:
                self._task.stop()
        except DaqError as exc:
            raise _wrap(exc)


def _names(collection) -> List[str]:
    try:
        return list(collection.channel_names)
    except DaqError:
        return []           # the device does not have this kind of channel


class NidaqmxBackend(Backend):
    name = "nidaqmx"

    def list_devices(self) -> List[DeviceInfo]:
        try:
            out = []
            for dev in System.local().devices:
                try:
                    rate = float(dev.ai_max_multi_chan_rate)
                except DaqError:
                    rate = None
                out.append(DeviceInfo(
                    name=dev.name, product_type=dev.product_type,
                    ai_channels=_names(dev.ai_physical_chans),
                    ao_channels=_names(dev.ao_physical_chans),
                    di_lines=_names(dev.di_lines), do_lines=_names(dev.do_lines),
                    counters=_names(dev.ci_physical_chans), max_ai_rate=rate))
            return out
        except Error as exc:        # includes DaqNotFoundError when the driver is not installed
            raise _wrap(exc)

    def create_ai(self, cfg: AIConfig) -> NidaqmxAI:
        cfg.validate()
        return NidaqmxAI(cfg)

    def create_ao(self, cfg: AOConfig) -> NidaqmxAO:
        cfg.validate()
        return NidaqmxAO(cfg)

    def create_di(self, cfg: DIOConfig) -> NidaqmxDI:
        cfg.validate()
        return NidaqmxDI(cfg)

    def create_do(self, cfg: DIOConfig) -> NidaqmxDO:
        cfg.validate()
        return NidaqmxDO(cfg)

    def create_counter(self, cfg: CounterConfig) -> NidaqmxCounter:
        cfg.validate()
        return NidaqmxCounter(cfg)
