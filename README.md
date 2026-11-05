# DAQScope

A free oscilloscope for data acquisition cards. You plug in an NI card, start DAQScope, and get
a scope screen with V/div and time/div knobs, an edge trigger, cursors and automatic
measurements. Underneath is a small Python library that hands you the same data as numpy arrays,
so whatever you see on screen you can also script.

![DAQScope showing four channels](docs/screenshot.png)

I started it because a PCIe-6321 on my bench had no free way to look at a signal quickly. NI MAX
test panels were not available on my machine, and the paid logging software is overkill when all
you want is to see a waveform and save it. DAQScope aims to be the quick look tool, and a clean
starting point if you want to build your own measurement program on top of it.

There is a simulated device built in. You can try everything, run the tests and develop new
features without any hardware.

DAQScope is an independent project. It is not affiliated with or endorsed by National Instruments.
For NI hardware you install the NI-DAQmx driver yourself, DAQScope does not ship it.

## Try it in two minutes

You need Python 3.9 or newer. A fresh environment keeps the Qt and numpy versions DAQScope brings
from clashing with your other projects.

With [uv](https://docs.astral.sh/uv/), which is the quickest:

```
git clone https://github.com/curlh/DAQScope.git
cd DAQScope
uv sync --extra gui --extra hdf5
uv run python -m daqscope
```

With conda or venv:

```
conda create -n daqscope python=3.12
conda activate daqscope
git clone https://github.com/curlh/DAQScope.git
cd DAQScope
pip install -e .[gui,hdf5]
python -m daqscope
```

A window opens with four simulated channels. Press Autoset and the traces settle on screen.

## Using it with a real card

Install the NI-DAQmx driver from National Instruments, then add the Python side in the same
environment and check that DAQScope can see your card.

```
pip install -e .[ni]
python examples/hardware_check.py
```

That script lists the devices it finds and reads one second from the first analog input, which
tells you quickly whether the driver and card are happy. Then start the scope on the real device:

```
python -m daqscope --backend nidaqmx
```

The NI backend is new. It follows the nidaqmx 1.x API and is covered by tests that run against a
stand-in for the driver, so the first run on a real card is the real test. If something misbehaves,
please open an issue with the device model and the error text.

On cards that share one converter between channels, such as the X series, the maximum sample rate
is divided between the channels you select. DAQScope only offers rates the card can do for the
current selection.

## What the scope does

The screen is a classic ten by eight divisions. Each channel has its own V/div and vertical
position, and the timebase goes from microseconds to a second per division in the usual 1, 2, 5
steps. Below the screen, a tile per channel shows its scale. Click a tile to hide the channel, or
scroll over it to change the scale like turning a knob. The timebase and trigger tiles work the
same way.

Triggering works on a rising or falling edge of any channel, with Auto, Normal and Single modes.
You can drag the trigger level line on the screen. Hysteresis is chosen automatically from the
noise on the signal, so a slow edge with some noise does not make the picture flip between phases.
The trigger point is interpolated between samples, which keeps the trace steady. At 100 ms per
division and slower the display rolls instead of triggering, like a real scope.

Autoset looks at the signals and picks V/div, position, trigger level and timebase for you. Two
pairs of cursors read out time differences, frequency and voltage differences. The measurement
table gives Vpp, maximum, minimum, mean, RMS, frequency, period and duty cycle per channel. At
slow timebases the display keeps narrow glitches visible instead of dropping them.

Record writes the incoming data to HDF5, CSV or npz while you watch. Writing happens on its own
thread, so a slow disk does not disturb the display. Save frame stores just what is on screen.

## Using it from Python

The library does not need the GUI. A minimal acquisition into numpy:

```python
from daqscope.backends import get_backend
from daqscope.core import AIChannel, AIConfig, AcquisitionSession

backend = get_backend("simulated")          # or "nidaqmx"
cfg = AIConfig([AIChannel("SimDev1/ai0"), AIChannel("SimDev1/ai1")], sample_rate=10_000)
with AcquisitionSession(backend, cfg) as session:
    data = session.read(10_000)             # numpy array, shape (2, 10000)
```

For continuous acquisition, a `StreamRunner` reads on a worker thread into a ring buffer and
hands every block to whoever subscribes, for example a file writer:

```python
from daqscope.core import StreamRunner
from daqscope.io import open_writer

with AcquisitionSession(backend, cfg) as session:
    runner = StreamRunner(session)
    with open_writer("run.h5", [c.name for c in cfg.channels], cfg.sample_rate) as writer:
        runner.subscribe(writer.put)
        runner.start()
        ...                                 # runner.buffer.latest(n) is the newest n samples
        runner.stop()
```

The trigger and timebase logic of the scope lives in `daqscope.core.ScopeEngine` and has no GUI
dependency, so you can use it in scripts too. Analog output, digital lines and counters are
available through the same backend object. See the `examples` folder for short runnable scripts.

## How it is put together

```
src/daqscope/
  core/        acquisition sessions, ring buffer, trigger and scope engine, measurements
  backends/    the backend interface, a simulated device and the NI-DAQmx backend
  io/          file writers and readers
  gui/         the scope window, built with PySide6 and pyqtgraph
examples/      small scripts, including a hardware check
tests/         pytest suite, runs without hardware
```

The core never imports the GUI or a hardware package. Only the NI backend imports `nidaqmx`, and
only `gui/qt.py` decides which Qt binding is used. To support another kind of hardware you
implement the interfaces in `backends/base.py` and register the backend in
`backends/__init__.py`. The simulated backend is a complete reference to copy from.

## Status and plans

The analog input scope, the simulated device, file recording and the NI backend are in place. The
GUI does not yet have panels for analog output, digital I/O and counters, although the backends
support them. Next on the list are those panels, an automatic sample rate that follows the
timebase, and choosing the hardware voltage range from V/div.

## Development

```
pip install -e .[dev,gui,hdf5]
pytest
```

Tests use the simulated backend and a fake of the NI driver. To look at the GUI on a machine
without a display, run with `QT_QPA_PLATFORM=offscreen`. See `CONTRIBUTING.md` for the ground
rules.

## License

MIT, see `LICENSE`.
