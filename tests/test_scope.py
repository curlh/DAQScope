import numpy as np
import pytest

from daqscope.core import (FrameAverager, RingBuffer, ScopeFrame, ScopeEngine, TriggerConfig, find_edges, measure,
                           minmax_decimate)

FS = 10_000.0


def sine(n, f, fs=FS, start=0, amp=1.0, phase=0.0):
    t = (start + np.arange(n)) / fs
    return amp * np.sin(2 * np.pi * f * t + phase)


def test_find_edges_sine():
    x = sine(1000, 100)                         # 100 Hz at 10 kS/s, period 100 samples
    up = find_edges(x, 0.0, "rising")
    dn = find_edges(x, 0.0, "falling")
    np.testing.assert_allclose(up[:3], [100, 200, 300], atol=1e-6)
    np.testing.assert_allclose(dn[:3], [50, 150, 250], atol=1e-6)


def test_find_edges_hysteresis_rejects_noise():
    rng = np.random.default_rng(0)
    x = sine(2000, 50) + rng.normal(0, 0.05, 2000)
    assert find_edges(x, 0.0, "rising", 0.0).size > 9      # noise retriggers inside each edge
    assert find_edges(x, 0.0, "rising", 0.3).size == 9     # 10 cycles in 0.2 s, the first starts at 0, one edge per later cycle


def test_decimate_keeps_glitch():
    y = np.zeros(100_000)
    y[54_321] = 5.0
    t = np.arange(y.size) / FS
    td, yd = minmax_decimate(t, y, 1000)
    assert yd.size <= 1000 and yd.max() == 5.0
    assert minmax_decimate(t[:500], y[:500], 1000)[1].size == 500


def test_decimate_covers_whole_trace():
    n = 10_000                                   # 10000 is not a multiple of the bin count
    t = np.arange(n) / FS
    y = np.arange(n, dtype=float)
    td, yd = minmax_decimate(t, y, 2040)
    assert yd.size <= 2040 + 2
    assert td[0] == t[0] and td[-1] == t[-1] and yd[-1] == n - 1
    assert np.all(np.diff(td) >= 0)


def test_measure_square():
    n = 10_000
    phase = (np.arange(n) / FS * 100) % 1.0
    y = np.where(phase < 0.25, 3.0, -1.0)
    m = measure(y, FS)
    assert m["max"] == 3.0 and m["min"] == -1.0 and m["pp"] == 4.0
    assert m["freq"] == pytest.approx(100.0, rel=1e-3)
    assert m["duty"] == pytest.approx(0.25, abs=0.01)
    assert m["rms"] == pytest.approx(np.sqrt(0.25 * 9 + 0.75 * 1), rel=1e-3)


def fill(buf, n_total, f=100.0, chunk=500):
    done = 0
    while done < n_total:
        m = min(chunk, n_total - done)
        buf.write(np.vstack([sine(m, f, start=done), sine(m, 2 * f, start=done)]))
        done += m


def test_trigger_frames_are_phase_locked():
    buf = RingBuffer(2, 100_000)
    eng = ScopeEngine(FS, 2)
    eng.time_per_div = 1e-3                 # 10 ms screen = one 100 Hz cycle
    eng.trigger = TriggerConfig(source=0, level=0.0, slope="rising", mode="normal")
    eng.run(buf)
    fill(buf, 3000, chunk=50)
    shots = []
    for _ in range(3):
        fr = eng.update(buf)
        assert fr is not None and fr.triggered
        shots.append(np.interp(0.0, fr.time, fr.data[0]))
        assert fr.data.shape == (2, 100)
        # next frame needs fresh data
        fill_more = 1000
        buf.write(np.vstack([sine(fill_more, 100, start=buf.total_written),
                             sine(fill_more, 200, start=buf.total_written)]))
    assert np.allclose(shots, 0.0, atol=1e-6)      # interpolated value at t=0 is the level


def test_normal_mode_waits_and_single_stops():
    buf = RingBuffer(1, 100_000)
    eng = ScopeEngine(FS, 1)
    eng.time_per_div = 1e-3
    eng.trigger = TriggerConfig(level=5.0, mode="normal")   # never reached
    eng.run(buf, now=0.0)
    buf.write(sine(3000, 100)[None, :])
    assert eng.update(buf, now=10.0) is None
    eng.trigger = TriggerConfig(level=0.5, mode="single")
    eng.run(buf, now=0.0)
    buf.write(sine(3000, 100, start=3000)[None, :])
    fr = eng.update(buf, now=0.1)
    assert fr is not None and not eng.running and eng.status == "Stop"
    assert eng.update(buf) is None


def test_auto_mode_free_runs_without_trigger():
    buf = RingBuffer(1, 100_000)
    eng = ScopeEngine(FS, 1)
    eng.time_per_div = 1e-3
    eng.trigger = TriggerConfig(level=5.0, mode="auto")
    eng.run(buf, now=0.0)
    buf.write(sine(3000, 100)[None, :])
    assert eng.update(buf, now=0.05) is None
    fr = eng.update(buf, now=0.5)
    assert fr is not None and not fr.triggered and eng.status == "Auto"


def test_roll_mode_pads_with_nan():
    buf = RingBuffer(1, 200_000)
    eng = ScopeEngine(FS, 1)
    eng.time_per_div = 0.2                  # 2 s screen = 20000 samples
    eng.run(buf, now=0.0)
    buf.write(sine(5000, 5)[None, :])
    fr = eng.update(buf, now=0.0)
    assert fr.rolling and fr.data.shape[1] == 20_000
    assert fr.valid_from == 15_000 and eng.status == "Roll"


def test_trigger_tracks_latest_without_lag():
    buf = RingBuffer(1, 100_000)
    eng = ScopeEngine(FS, 1)
    eng.time_per_div = 1e-3
    eng.trigger = TriggerConfig(mode="normal")
    eng.run(buf)
    buf.write(sine(20_000, 100)[None, :])          # two seconds' worth of cycles queued up
    fr = eng.update(buf)
    # the frame comes from the newest cycle, not from the oldest unprocessed one
    assert eng._consumed > 19_000


def test_status_stays_triggered_while_triggers_arrive():
    buf = RingBuffer(1, 100_000)
    eng = ScopeEngine(FS, 1)
    eng.time_per_div = 1e-3
    eng.trigger = TriggerConfig(mode="normal")
    eng.run(buf, now=0.0)
    buf.write(sine(3000, 100)[None, :])
    assert eng.update(buf, now=0.01) is not None and eng.status == "Trig'd"
    assert eng.update(buf, now=0.02) is None and eng.status == "Trig'd"
    assert eng.update(buf, now=1.0) is None and eng.status == "Ready"


def test_slow_noisy_edge_does_not_flip_phase():
    # 10 Hz at 50 kS/s with 10 mV noise: slope per sample is far below the noise
    rng = np.random.default_rng(5)
    fs = 50_000.0
    buf = RingBuffer(1, 400_000)
    eng = ScopeEngine(fs, 1)
    eng.time_per_div = 2e-3
    eng.trigger = TriggerConfig(mode="normal")      # automatic hysteresis
    eng.run(buf)
    done, rising = 0, 0
    frames = 0
    while frames < 12 and done < 300_000:
        n = 1000
        t = (done + np.arange(n)) / fs
        buf.write((np.sin(2 * np.pi * 10 * t) + rng.normal(0, 0.01, n))[None, :])
        done += n
        fr = eng.update(buf)
        if fr is not None:
            frames += 1
            mid = fr.data.shape[1] // 2
            rising += fr.data[0, mid - 150:mid - 100].mean() < 0 < fr.data[0, mid + 100:mid + 150].mean()
    assert frames >= 8 and rising == frames


def test_edges_not_missed_when_many_samples_arrive_between_updates():
    fs = 250_000.0
    buf = RingBuffer(1, 2_000_000)
    eng = ScopeEngine(fs, 1)
    eng.time_per_div = 2e-4                         # 500-sample screen
    eng.trigger = TriggerConfig(mode="normal", hysteresis=0.0)
    eng.run(buf)
    got, done = 0, 0
    while done < 250_000:                           # 5000 samples per update, 10x the screen
        n = 5000
        t = (done + np.arange(n)) / fs
        buf.write(np.sin(2 * np.pi * 50 * t + 0.3)[None, :])
        done += n
        got += eng.update(buf) is not None
    assert got >= 45                                # one 50 Hz edge per 5000 samples


def test_find_edges_resumes_across_pieces():
    rng = np.random.default_rng(2)
    x = np.sin(2 * np.pi * 10 * np.arange(60_000) / 250_000.0) + rng.normal(0, 0.01, 60_000)
    whole = find_edges(x, 0.0, "rising", 0.06)
    found, state, a = [], 0, 0
    while a < x.size - 1:
        b = min(a + 3000, x.size - 1)             # pieces share one sample
        e, state = find_edges(x[a:b + 1], 0.0, "rising", 0.06, state, return_state=True)
        found += list(a + e)
        a = b
    np.testing.assert_allclose(found, whole)


def test_measure_frequency_with_one_rising_edge():
    # exactly two cycles, starting and ending on the rising crossing: one rising edge is inside
    n = 20_000
    y = np.sin(2 * np.pi * 10 * (np.arange(n) + 0.5) / FS)[: n - 1]     # 10 Hz, 0.2 s window
    assert measure(y, FS)["freq"] == pytest.approx(10.0, rel=1e-3)


def test_averager_reduces_noise_and_keeps_trigger_aligned():
    rng = np.random.default_rng(7)
    pre, span, sigma, n = 500, 1000, 0.01, 16
    avg = FrameAverager(n)
    f = lambda t: np.sin(2 * np.pi * 100 * t)          # 100 Hz, the trigger sits at t = 0
    out = None
    for _ in range(40):
        frac = rng.uniform(0, 1)                       # sub-sample trigger offset of this frame
        t = (np.arange(span) - pre - frac) / FS
        fr = ScopeFrame((f(t) + rng.normal(0, sigma, span))[None, :], FS, pre, frac, True, False)
        out = avg.add(fr)
    t0 = (np.arange(span) - pre) / FS
    resid = out.data[0] - f(t0)
    assert resid.std() == pytest.approx(sigma / np.sqrt(n), rel=0.2)
    assert out.frac == 0.0 and out.data.shape == (1, span)


def test_averager_passes_through_untriggered_frames():
    avg = FrameAverager(8)
    fr = ScopeFrame(np.zeros((1, 50)), FS, 25, 0.0, False, False)
    assert avg.add(fr) is fr
    assert FrameAverager(1).add(ScopeFrame(np.zeros((1, 50)), FS, 25, 0.3, True, False)).frac == 0.3
