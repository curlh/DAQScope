"""Backend interface. A backend turns configs into hardware (or simulated) tasks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Sequence

import numpy as np

from ..core.config import (AIConfig, AOConfig, CounterConfig, DeviceInfo,
                           DIOConfig)


class AnalogInputTask(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def read(self, n_samples: int, timeout: float = 10.0) -> np.ndarray:
        """Return the next n_samples as float array (n_channels, n_samples), in volts."""

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class AnalogOutputTask(ABC):
    @abstractmethod
    def write_point(self, values: Sequence[float]) -> None:
        """Set each channel to a constant voltage."""

    @abstractmethod
    def start_waveform(self, samples: np.ndarray, sample_rate: float) -> None:
        """Regenerate samples (n_channels, n_samples) continuously until stop()."""

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class DigitalInputTask(ABC):
    @abstractmethod
    def read(self) -> np.ndarray:
        """Return the current state of every line as a bool array."""

    @abstractmethod
    def close(self) -> None: ...


class DigitalOutputTask(ABC):
    @abstractmethod
    def write(self, values: Sequence[bool]) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class CounterInputTask(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def read(self) -> float:
        """Edge count so far (edges mode) or measured frequency in Hz (frequency mode)."""

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class Backend(ABC):
    name = "base"

    @abstractmethod
    def list_devices(self) -> List[DeviceInfo]: ...

    @abstractmethod
    def create_ai(self, cfg: AIConfig) -> AnalogInputTask: ...

    @abstractmethod
    def create_ao(self, cfg: AOConfig) -> AnalogOutputTask: ...

    @abstractmethod
    def create_di(self, cfg: DIOConfig) -> DigitalInputTask: ...

    @abstractmethod
    def create_do(self, cfg: DIOConfig) -> DigitalOutputTask: ...

    @abstractmethod
    def create_counter(self, cfg: CounterConfig) -> CounterInputTask: ...
