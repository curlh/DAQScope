# DAQScope

An open-source oscilloscope-style GUI and acquisition library for data acquisition (DAQ) devices.
Data arrives as numpy arrays, the hardware layer is a thin replaceable backend, and a simulated
device lets you develop, test and run CI without any hardware.

DAQScope is an independent project. It is not affiliated with, endorsed by, or sponsored by
National Instruments. To use NI hardware you must install the NI-DAQmx driver yourself. DAQScope
does not ship or redistribute it.

## Status

Early development (version 0.1 dev).

| Area | State |
| --- | --- |
| Core library (config, sessions, ring buffer, trigger, measurements) | done |
| Simulated backend (AI, AO, digital I/O, counters) | done |
| File writers and readers (npz, HDF5, CSV) | done |
| Oscilloscope GUI for analog input | done, tested on the simulated device |
| NI-DAQmx backend | planned, needs testing on real hardware |
| GUI panels for analog output, digital I/O and counters | planned |

## Installation

Python 3.9 or newer.

```
git clone https://github.com/curlh/DAQScope.git
cd DAQScope
pip install -e .[gui,hdf5]
```

Optional extras: `gui` (PySide6, pyqtgraph), `hdf5` (h5py), `ni` (nidaqmx), `dev` (pytest).

For NI hardware, install the NI-DAQmx driver from National Instruments first, then
`pip install -e .[ni]`.

## Oscilloscope GUI

```
python -m daqscope                    # simulated device
python -m daqscope --backend nidaqmx  # real hardware, once the backend is available
```

The screen is a 10 x 8 division display. The controls follow a bench oscilloscope.

- Vertical: per-channel enable, V/div (1 mV to 5 V in a 1-2-5 sequence) and position.
- Horizontal: time/div in a 1-2-5 sequence and trigger position. Auto mode rolls the display at
  100 ms/div and slower.
- Trigger: source channel, rising or falling edge, level, hysteresis, and Auto, Normal or Single
  mode. The trigger point is interpolated between samples, so the trace does not jitter. The
  level line on the screen can be dragged.
- Run/Stop, Single and Autoset (picks V/div, position, trigger level and time/div from the signal).
- Two pairs of cursors with delta time, 1/delta time and delta voltage.
- Automatic measurements per channel: Vpp, max, min, mean, RMS, frequency, period and duty cycle.
- Peak-detect display, so narrow glitches stay visible at slow timebases.
- Record to HDF5, CSV or npz on a background thread, and save the current frame.

The sample rate is set in the Acquisition panel. On multiplexed cards the maximum rate is shared
between the selected channels.

## Using the library

```python
from daqscope.backends import get_backend
from daqscope.core import AIChannel, AIConfig, AcquisitionSession

backend = get_backend("simulated")        # "nidaqmx" for real hardware
cfg = AIConfig([AIChannel("SimDev1/ai0"), AIChannel("SimDev1/ai1")], sample_rate=10_000)
with AcquisitionSession(backend, cfg) as session:
    data = session.read(10_000)           # numpy array, shape (n_channels, 10000)
```

Continuous acquisition with recording on a background thread:

```python
from daqscope.core import StreamRunner
from daqscope.io import open_writer

with AcquisitionSession(backend, cfg) as session:
    runner = StreamRunner(session)
    with open_writer("run.h5", [c.name for c in cfg.channels], cfg.sample_rate) as writer:
        runner.subscribe(writer.put)
        runner.start()
        ...                               # runner.buffer.latest(n) gives the newest samples
        runner.stop()
```

The oscilloscope trigger and timebase logic (`daqscope.core.ScopeEngine`) has no GUI dependency
and can be used from scripts. More examples are in `examples/`.

## Project layout

```
src/daqscope/
  core/        config, sessions, ring buffer, trigger, scope engine, measurements, waveforms
  backends/    backend interface, simulated backend, NI-DAQmx backend (planned)
  io/          background file writers and readers
  gui/         oscilloscope window (PySide6 and pyqtgraph)
  app.py       command line entry point
examples/      scripts that run on the simulated device
tests/         pytest suite, runs without hardware
```

`core` does not import hardware or GUI packages. Only the NI-DAQmx backend imports `nidaqmx`, and
only `gui/qt.py` chooses the Qt binding.

## Adding a backend

Implement the interfaces in `daqscope/backends/base.py` (`Backend` and the AI, AO, DI, DO and
counter task classes) and register the backend in `daqscope/backends/__init__.py`. The simulated
backend in `simulated.py` is a complete reference.

## Development

```
pip install -e .[dev,gui,hdf5]
pytest
```

The tests use the simulated backend. The GUI can be checked without a display by running with
`QT_QPA_PLATFORM=offscreen`. See `CONTRIBUTING.md`.

## License

MIT, see `LICENSE`.
