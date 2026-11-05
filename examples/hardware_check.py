"""Quick check of a real NI device: list devices, read a short block from the first AI channel.

Usage: python hardware_check.py [device_name]
"""
import sys

import numpy as np

from daqscope.backends import get_backend
from daqscope.core import AIChannel, AIConfig, AcquisitionSession

backend = get_backend("nidaqmx")
devices = backend.list_devices()
if not devices:
    sys.exit("no NI devices found")
for d in devices:
    print(f"{d.name}: {d.product_type}, {len(d.ai_channels)} AI, {len(d.ao_channels)} AO, "
          f"{len(d.di_lines)} DI, {len(d.do_lines)} DO, {len(d.counters)} counters, "
          f"max AI rate {d.max_ai_rate}")
dev = next((d for d in devices if len(sys.argv) < 2 or d.name == sys.argv[1]), devices[0])
chan = dev.ai_channels[0]
cfg = AIConfig([AIChannel(chan, terminal="DEFAULT", min_val=-10, max_val=10)], sample_rate=10_000)
with AcquisitionSession(backend, cfg) as session:
    data = session.read(10_000)
print(f"{chan}: mean {np.mean(data):.4f} V, std {np.std(data):.4f} V, "
      f"min {data.min():.4f} V, max {data.max():.4f} V")
