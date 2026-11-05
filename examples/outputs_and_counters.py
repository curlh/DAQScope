"""Analog output, digital I/O and counters on the simulated device."""
import time

from daqscope.backends import get_backend
from daqscope.core import AOChannel, AOConfig, CounterConfig, DIOConfig, one_period

b = get_backend("simulated")
ao = b.create_ao(AOConfig([AOChannel("SimDev1/ao0")]))
ao.write_point([1.5])
wave, f = one_period("sine", 100, 10_000, amplitude=2.0)
ao.start_waveform(wave[None, :], 10_000)
print("sine output at", f, "Hz")
ao.close()

do = b.create_do(DIOConfig(["SimDev1/port1/line0", "SimDev1/port1/line1"]))
do.write([True, False])
di = b.create_di(DIOConfig(["SimDev1/port0/line0", "SimDev1/port0/line1"]))
print("digital in", di.read())

ctr = b.create_counter(CounterConfig("SimDev1/ctr0", mode="edges"))
ctr.start()
time.sleep(0.5)
print("edges", ctr.read())
