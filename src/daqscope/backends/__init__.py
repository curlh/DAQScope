from __future__ import annotations

from .base import Backend
from ..core.errors import ConfigError


def get_backend(name: str = "simulated") -> Backend:
    """Return a backend by name. Hardware backends are imported only when requested."""
    if name == "simulated":
        from .simulated import SimulatedBackend
        return SimulatedBackend()
    if name == "nidaqmx":
        from .nidaqmx_backend import NidaqmxBackend   # needs the nidaqmx package and driver
        return NidaqmxBackend()
    raise ConfigError(f"unknown backend {name!r}")


def available_backends() -> list:
    """Backends that can be created on this machine."""
    from importlib.util import find_spec
    names = ["simulated"]
    if find_spec("nidaqmx") is not None and find_spec("daqscope.backends.nidaqmx_backend") is not None:
        names.append("nidaqmx")
    return names
