"""Acquire one second from two channels into a numpy array (simulated device)."""
from daqscope.backends import get_backend
from daqscope.core import AIChannel, AIConfig, AcquisitionSession

backend = get_backend("simulated")        # use "nidaqmx" with a real device
cfg = AIConfig([AIChannel("SimDev1/ai0"), AIChannel("SimDev1/ai1")], sample_rate=10_000)
with AcquisitionSession(backend, cfg) as session:
    data = session.read(10_000)
print(data.shape, data.mean(axis=1), data.std(axis=1))
