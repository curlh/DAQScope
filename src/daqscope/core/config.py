"""Plain data classes describing tasks. No hardware or GUI imports here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .errors import ConfigError

TERMINALS = ("DEFAULT", "RSE", "NRSE", "DIFF", "PSEUDO_DIFF")


@dataclass
class Scale:
    """Linear scaling y = gain * x + offset applied after acquisition."""
    gain: float = 1.0
    offset: float = 0.0
    unit: str = "V"


@dataclass
class AIChannel:
    name: str                      # physical channel, e.g. "Dev1/ai0"
    label: str = ""                # display name, falls back to name
    min_val: float = -10.0
    max_val: float = 10.0
    terminal: str = "DEFAULT"
    scale: Scale = field(default_factory=Scale)

    @property
    def display(self) -> str:
        return self.label or self.name

    def validate(self) -> None:
        if self.min_val >= self.max_val:
            raise ConfigError(f"{self.name}: min_val must be below max_val")
        if self.terminal not in TERMINALS:
            raise ConfigError(f"{self.name}: unknown terminal {self.terminal!r}")


@dataclass
class AIConfig:
    channels: List[AIChannel]
    sample_rate: float = 1000.0    # S/s per channel

    def validate(self) -> None:
        if not self.channels:
            raise ConfigError("at least one AI channel is required")
        if self.sample_rate <= 0:
            raise ConfigError("sample_rate must be positive")
        for ch in self.channels:
            ch.validate()

    @property
    def n_channels(self) -> int:
        return len(self.channels)


@dataclass
class AOChannel:
    name: str
    min_val: float = -10.0
    max_val: float = 10.0

    def validate(self) -> None:
        if self.min_val >= self.max_val:
            raise ConfigError(f"{self.name}: min_val must be below max_val")


@dataclass
class AOConfig:
    channels: List[AOChannel]

    def validate(self) -> None:
        if not self.channels:
            raise ConfigError("at least one AO channel is required")
        for ch in self.channels:
            ch.validate()


@dataclass
class DIOConfig:
    lines: List[str]               # e.g. ["Dev1/port0/line0", "Dev1/port0/line1"]

    def validate(self) -> None:
        if not self.lines:
            raise ConfigError("at least one digital line is required")


@dataclass
class CounterConfig:
    channel: str                   # e.g. "Dev1/ctr0"
    mode: str = "edges"            # "edges" or "frequency"
    edge: str = "rising"           # "rising" or "falling"
    min_freq: float = 1.0          # frequency mode only, Hz
    max_freq: float = 100_000.0

    def validate(self) -> None:
        if self.mode not in ("edges", "frequency"):
            raise ConfigError(f"unknown counter mode {self.mode!r}")
        if self.edge not in ("rising", "falling"):
            raise ConfigError(f"unknown edge {self.edge!r}")
        if self.min_freq <= 0 or self.min_freq >= self.max_freq:
            raise ConfigError("need 0 < min_freq < max_freq")


@dataclass
class DeviceInfo:
    name: str
    product_type: str = ""
    ai_channels: List[str] = field(default_factory=list)
    ao_channels: List[str] = field(default_factory=list)
    di_lines: List[str] = field(default_factory=list)
    do_lines: List[str] = field(default_factory=list)
    counters: List[str] = field(default_factory=list)
    max_ai_rate: Optional[float] = None   # aggregate S/s
