# Contributing

- Keep `daqscope.core` free of hardware and GUI imports. Only `backends/nidaqmx_backend.py`
  may import `nidaqmx`, and only `gui/qt.py` may import PySide6.
- New hardware support is a new backend implementing the interfaces in `backends/base.py`.
- Every feature needs a test that runs against the simulated backend.
- Run `pytest` before opening a pull request.
