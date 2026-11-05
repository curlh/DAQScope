class DAQScopeError(Exception):
    """Base class for all DAQScope errors."""


class BackendError(DAQScopeError):
    """The hardware or simulated backend reported a failure."""


class ConfigError(DAQScopeError):
    """A task configuration is invalid."""
