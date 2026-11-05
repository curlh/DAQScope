"""Stream for three seconds and write the data to disk on a background thread."""
import time

from daqscope.backends import get_backend
from daqscope.core import AIChannel, AIConfig, AcquisitionSession, StreamRunner
from daqscope.io import open_writer, read_recording

cfg = AIConfig([AIChannel("SimDev1/ai0"), AIChannel("SimDev1/ai1")], sample_rate=20_000)
with AcquisitionSession(get_backend(), cfg) as session:
    runner = StreamRunner(session)
    with open_writer("recording.h5", [c.name for c in cfg.channels], cfg.sample_rate) as writer:
        runner.subscribe(writer.put)
        runner.start()
        time.sleep(3)
        runner.stop()
rec = read_recording("recording.h5")
print(rec.data.shape, rec.sample_rate, rec.start_time)
