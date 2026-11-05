"""Oscilloscope main window: screen, front-panel controls, measurements and recording."""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from ..backends import available_backends, get_backend
from ..core import (AcquisitionSession, AIChannel, AIConfig, ScopeEngine, StreamRunner,
                    TriggerConfig, measure)
from ..core.scope import DIVS_X
from ..io import open_writer
from .qt import QtCore, QtGui, QtWidgets, QTimer, Qt
from .scope_view import COLORS, ChannelView, ScopeView
from .units import ceil_125, eng, steps_125

W = QtWidgets
RATES = [1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 2.5e5]
MEASURES = [("Vpp", "pp", "V"), ("Max", "max", "V"), ("Min", "min", "V"), ("Mean", "mean", "V"),
            ("RMS", "rms", "V"), ("Freq", "freq", "Hz"), ("Period", "period", "s"), ("Duty", "duty", "")]
BUFFER_SECONDS = 20.0
BUFFER_MAX_SAMPLES = 16_000_000      # total float64 values, about 128 MB


def _spin(lo, hi, step, decimals, suffix=""):
    s = W.QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


class MainWindow(W.QMainWindow):
    def __init__(self, backend_name: str = "simulated"):
        super().__init__()
        self.setWindowTitle("DAQScope")
        self.resize(1400, 820)
        self.backend = get_backend(backend_name)
        self.session: Optional[AcquisitionSession] = None
        self.runner: Optional[StreamRunner] = None
        self.engine: Optional[ScopeEngine] = None
        self.writer = None
        self.names: List[str] = []
        self.channels: List[ChannelView] = []
        self._saved = {}                 # per channel name: (vdiv, pos), kept across re-applies
        self._rows = []
        self._frame = None
        self._last_measure = 0.0
        self._last_status = ""
        self._loading = False
        self._build_ui()
        self._fill_backends(backend_name)
        self._fill_devices()
        self.apply_acquisition()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(20)

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        self.view = ScopeView()
        self.view.triggerLevelMoved.connect(self._level_dragged)
        self.view.cursorsMoved.connect(self._update_cursor_readout)
        self.info = W.QLabel()
        self.info.setTextFormat(Qt.RichText)
        self.info.setStyleSheet("background:#111; padding:4px; font-family:monospace;")
        centre = W.QWidget()
        lay = W.QVBoxLayout(centre)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.info)
        self.setCentralWidget(centre)

        tb = self.addToolBar("Main")
        tb.setMovable(False)
        self.run_btn = W.QPushButton("RUN")
        self.run_btn.setMinimumWidth(70)
        self.run_btn.clicked.connect(self._toggle_run)
        self.single_btn = W.QPushButton("Single")
        self.single_btn.clicked.connect(self._single)
        self.auto_btn = W.QPushButton("Autoset")
        self.auto_btn.clicked.connect(self._autoset)
        self.rec_btn = W.QPushButton("Record")
        self.rec_btn.clicked.connect(self._toggle_record)
        self.save_btn = W.QPushButton("Save frame")
        self.save_btn.clicked.connect(self._save_frame)
        for b in (self.run_btn, self.single_btn, self.auto_btn, self.rec_btn, self.save_btn):
            tb.addWidget(b)

        panel = W.QWidget()
        pl = W.QVBoxLayout(panel)
        pl.addWidget(self._acq_group())
        pl.addWidget(self._vertical_group())
        pl.addWidget(self._horizontal_group())
        pl.addWidget(self._trigger_group())
        pl.addWidget(self._cursor_group())
        pl.addWidget(self._measure_group())
        pl.addStretch(1)
        scroll = W.QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(330)
        dock = W.QDockWidget("Controls", self)
        dock.setWidget(scroll)
        dock.setFeatures(W.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.statusBar().showMessage("")

    def _acq_group(self):
        g = W.QGroupBox("Acquisition")
        f = W.QFormLayout(g)
        self.backend_box = W.QComboBox()
        self.backend_box.activated.connect(self._backend_changed)
        self.device_box = W.QComboBox()
        self.device_box.activated.connect(lambda *_: self._fill_channels())
        self.chan_list = W.QListWidget()
        self.chan_list.setMaximumHeight(110)
        self.chan_list.itemChanged.connect(lambda *_: self._fill_rates())
        self.rate_box = W.QComboBox()
        self.apply_btn = W.QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_acquisition)
        f.addRow("Backend", self.backend_box)
        f.addRow("Device", self.device_box)
        f.addRow("Channels", self.chan_list)
        f.addRow("Sample rate", self.rate_box)
        f.addRow(self.apply_btn)
        return g

    def _vertical_group(self):
        g = W.QGroupBox("Vertical")
        self.vgrid = W.QGridLayout(g)
        return g

    def _horizontal_group(self):
        g = W.QGroupBox("Horizontal")
        f = W.QFormLayout(g)
        self.tdiv_box = W.QComboBox()
        self.tdiv_box.activated.connect(self._changed)
        self.tpos_spin = _spin(0, 100, 5, 0, " %")
        self.tpos_spin.setValue(50)
        self.tpos_spin.valueChanged.connect(self._changed)
        f.addRow("Time/div", self.tdiv_box)
        f.addRow("Trigger position", self.tpos_spin)
        return g

    def _trigger_group(self):
        g = W.QGroupBox("Trigger")
        f = W.QFormLayout(g)
        self.src_box = W.QComboBox()
        self.src_box.activated.connect(self._changed)
        self.slope_box = W.QComboBox()
        self.slope_box.addItems(["Rising", "Falling"])
        self.slope_box.activated.connect(self._changed)
        self.mode_box = W.QComboBox()
        self.mode_box.addItems(["Auto", "Normal", "Single"])
        self.mode_box.activated.connect(self._changed)
        self.level_spin = _spin(-100, 100, 0.1, 4, " V")
        self.level_spin.valueChanged.connect(self._changed)
        self.hyst_spin = _spin(0, 100, 0.01, 4, " V")
        self.hyst_spin.valueChanged.connect(self._changed)
        f.addRow("Source", self.src_box)
        f.addRow("Slope", self.slope_box)
        f.addRow("Mode", self.mode_box)
        f.addRow("Level", self.level_spin)
        f.addRow("Hysteresis", self.hyst_spin)
        return g

    def _cursor_group(self):
        g = W.QGroupBox("Cursors")
        v = W.QVBoxLayout(g)
        row = W.QHBoxLayout()
        self.cur_chk = W.QCheckBox("On")
        self.cur_chk.toggled.connect(self._cursors_toggled)
        self.cur_src = W.QComboBox()
        self.cur_src.activated.connect(self._update_cursor_readout)
        row.addWidget(self.cur_chk)
        row.addWidget(self.cur_src, 1)
        self.cur_label = W.QLabel("")
        self.cur_label.setStyleSheet("font-family:monospace;")
        v.addLayout(row)
        v.addWidget(self.cur_label)
        return g

    def _measure_group(self):
        g = W.QGroupBox("Measurements")
        v = W.QVBoxLayout(g)
        self.table = W.QTableWidget(len(MEASURES), 0)
        self.table.setVerticalHeaderLabels([m[0] for m in MEASURES])
        self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(W.QAbstractItemView.NoSelection)
        self.table.setMinimumHeight(250)
        v.addWidget(self.table)
        return g

    # ----------------------------------------------------------- acquisition
    def _fill_backends(self, current: str) -> None:
        self.backend_box.clear()
        self.backend_box.addItems(available_backends())
        self.backend_box.setCurrentText(current)

    def _backend_changed(self, *_):
        try:
            self.backend = get_backend(self.backend_box.currentText())
        except Exception as exc:
            W.QMessageBox.critical(self, "Backend", str(exc))
            return
        self._fill_devices()

    def _fill_devices(self) -> None:
        self.device_box.clear()
        try:
            self.devices = self.backend.list_devices()
        except Exception as exc:
            self.devices = []
            W.QMessageBox.critical(self, "Devices", str(exc))
        for d in self.devices:
            self.device_box.addItem(f"{d.name}  {d.product_type}".strip(), d)
        self._fill_channels()

    def _fill_channels(self) -> None:
        self.chan_list.blockSignals(True)
        self.chan_list.clear()
        dev = self.device_box.currentData()
        for i, name in enumerate(dev.ai_channels if dev else []):
            it = W.QListWidgetItem(name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if i < 4 else Qt.Unchecked)
            self.chan_list.addItem(it)
        self.chan_list.blockSignals(False)
        self._fill_rates()

    def _checked_channels(self) -> List[str]:
        return [self.chan_list.item(i).text() for i in range(self.chan_list.count())
                if self.chan_list.item(i).checkState() == Qt.Checked]

    def _fill_rates(self) -> None:
        dev = self.device_box.currentData()
        n = max(1, len(self._checked_channels()))
        keep = self.rate_box.currentData()
        self.rate_box.clear()
        # the card's maximum rate is shared between the scanned channels
        for r in RATES:
            if dev is None or dev.max_ai_rate is None or r * n <= dev.max_ai_rate:
                self.rate_box.addItem(eng(r, "S/s"), r)
        i = self.rate_box.findData(keep if keep else 1e5)
        self.rate_box.setCurrentIndex(i if i >= 0 else self.rate_box.count() - 1)

    def _teardown(self) -> None:
        if self.runner is not None:
            self.runner.stop()
        if self.session is not None:
            self.session.close()
        self.runner = self.session = self.engine = None

    def apply_acquisition(self) -> None:
        self._stop_recording()
        names = self._checked_channels()
        fs = self.rate_box.currentData()
        if not names or fs is None:
            W.QMessageBox.warning(self, "Acquisition", "Select at least one channel.")
            return
        for ch, nm in zip(self.channels, self.names):
            self._saved[nm] = (ch.vdiv, ch.pos)
        self._teardown()
        try:
            cfg = AIConfig([AIChannel(n) for n in names], sample_rate=fs)
            self.session = AcquisitionSession(self.backend, cfg)
            secs = min(BUFFER_SECONDS, BUFFER_MAX_SAMPLES / (len(names) * fs))
            self.runner = StreamRunner(self.session, block_seconds=0.02, buffer_seconds=secs)
            self.runner.start()
        except Exception as exc:
            self._teardown()
            W.QMessageBox.critical(self, "Acquisition", str(exc))
            return
        self.names = names
        n = len(names)
        self.engine = ScopeEngine(fs, n)
        self.channels = []
        for i, nm in enumerate(names):
            vdiv, pos = self._saved.get(nm, (1.0, ((n - 1) / 2 - i) * 1.6))
            self.channels.append(ChannelView(True, vdiv, pos))
        self.view.set_channel_count(n)
        self._frame = None
        self._build_channel_rows()
        self._fill_timebase()
        self._loading = True
        for box in (self.src_box, self.cur_src):
            box.clear()
            box.addItems([f"CH{i + 1}  {nm.split('/')[-1]}" for i, nm in enumerate(names)])
        self.table.setColumnCount(n)
        self.table.setHorizontalHeaderLabels([f"CH{i + 1}" for i in range(n)])
        self._loading = False
        self.engine.run(self.runner.buffer)
        self._changed()
        self.statusBar().showMessage(f"{self.backend.name}  {n} ch  {eng(fs, 'S/s')} per channel")

    def _build_channel_rows(self) -> None:
        while self.vgrid.count():
            w = self.vgrid.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._rows = []
        for i, nm in enumerate(self.names):
            chk = W.QCheckBox(f"CH{i + 1}")
            chk.setChecked(self.channels[i].enabled)
            chk.setStyleSheet(f"color:{COLORS[i % len(COLORS)]}; font-weight:bold;")
            vbox = W.QComboBox()
            for v in steps_125(1e-3, 5.0):
                vbox.addItem(eng(v, "V") + "/div", v)
            vbox.setCurrentIndex(max(0, vbox.findData(self.channels[i].vdiv)))
            pos = _spin(-4, 4, 0.1, 2, " div")
            pos.setValue(self.channels[i].pos)
            chk.toggled.connect(self._changed)
            vbox.activated.connect(self._changed)
            pos.valueChanged.connect(self._changed)
            self.vgrid.addWidget(chk, i, 0)
            self.vgrid.addWidget(vbox, i, 1)
            self.vgrid.addWidget(pos, i, 2)
            self._rows.append((chk, vbox, pos))

    def _fill_timebase(self) -> None:
        keep = self.tdiv_box.currentData() or 2e-2
        fs = self.engine.sample_rate
        # at least 10 samples per division, and a screen that fits the buffer
        values = steps_125(10 / fs, self.engine.max_time_per_div(self.runner.buffer))
        self.tdiv_box.clear()
        for v in values:
            self.tdiv_box.addItem(eng(v, "s") + "/div", v)
        best = min(range(len(values)), key=lambda i: abs(np.log(values[i] / keep)))
        self.tdiv_box.setCurrentIndex(best)

    # ----------------------------------------------------------- front panel
    def _changed(self, *_) -> None:
        if self._loading or self.engine is None:
            return
        for ch, (chk, vbox, pos) in zip(self.channels, self._rows):
            ch.enabled = chk.isChecked()
            ch.vdiv = vbox.currentData()
            ch.pos = pos.value()
        e = self.engine
        e.time_per_div = self.tdiv_box.currentData()
        e.trigger_pos = self.tpos_spin.value() / 100
        src = max(0, self.src_box.currentIndex())
        e.trigger = TriggerConfig(src, self.level_spin.value(),
                                  self.slope_box.currentText().lower(),
                                  self.mode_box.currentText().lower(), self.hyst_spin.value())
        self.level_spin.setSingleStep(self.channels[src].vdiv / 10)
        self.hyst_spin.setSingleStep(self.channels[src].vdiv / 10)
        self._refresh()

    def _refresh(self) -> None:
        e = self.engine
        self.view.redraw(self.channels, e.time_per_div, e.trigger_pos, e.trigger.source, e.trigger.level)
        parts = []
        for i, ch in enumerate(self.channels):
            if ch.enabled:
                parts.append(f"<span style='color:{COLORS[i % len(COLORS)]}'>CH{i + 1} {eng(ch.vdiv, 'V')}/div</span>")
        t = e.trigger
        parts.append(f"<span style='color:#ccc'>Time {eng(e.time_per_div, 's')}/div &nbsp; "
                     f"Trig CH{t.source + 1} {t.slope} {eng(t.level, 'V')} {t.mode} &nbsp; "
                     f"{eng(e.sample_rate, 'S/s')}</span>")
        self.info.setText(" &nbsp;&nbsp; ".join(parts))
        self._update_cursor_readout()

    def _level_dragged(self, ydiv: float) -> None:
        if self.engine is None:
            return
        ch = self.channels[self.engine.trigger.source]
        self.level_spin.setValue((ydiv - ch.pos) * ch.vdiv)      # valueChanged runs _changed

    def _toggle_run(self) -> None:
        if self.engine is None:
            return
        if self.engine.running:
            self.engine.stop()
        else:
            self.engine.run(self.runner.buffer)

    def _single(self) -> None:
        if self.engine is None:
            return
        self.mode_box.setCurrentText("Single")
        self._changed()
        self.engine.run(self.runner.buffer)

    def _autoset(self) -> None:
        if self.engine is None or self.runner is None:
            return
        fs = self.engine.sample_rate
        data = self.runner.buffer.latest(int(fs * 0.5))
        if data.shape[1] < 100:
            return
        self._loading = True
        for i, (ch, (chk, vbox, pos)) in enumerate(zip(self.channels, self._rows)):
            if not ch.enabled:
                continue
            m = measure(data[i], fs)
            if not np.isfinite(m["pp"]):
                continue
            vdiv = min(5.0, max(1e-3, ceil_125(max(m["pp"], 1e-6) / 6)))     # signal fills 6 of 8 divisions
            vbox.setCurrentIndex(vbox.findData(vdiv))
            pos.setValue(-(m["max"] + m["min"]) / 2 / vdiv)
            if i == max(0, self.src_box.currentIndex()):
                self.level_spin.setValue((m["max"] + m["min"]) / 2)
                if np.isfinite(m["freq"]):
                    want = 3 / m["freq"] / DIVS_X                          # three cycles on screen
                    j = min(range(self.tdiv_box.count()),
                            key=lambda k: abs(np.log(self.tdiv_box.itemData(k) / want)))
                    self.tdiv_box.setCurrentIndex(j)
        self.mode_box.setCurrentText("Auto")
        self.tpos_spin.setValue(50)
        self._loading = False
        self._changed()
        self.engine.run(self.runner.buffer)

    # --------------------------------------------------------------- cursors
    def _cursors_toggled(self, on: bool) -> None:
        self.view.show_cursors(on)
        self._update_cursor_readout()

    def _update_cursor_readout(self, *_) -> None:
        if not self.cur_chk.isChecked() or self.engine is None or not self.channels:
            self.cur_label.setText("")
            return
        ch = self.channels[max(0, self.cur_src.currentIndex())]
        td = self.engine.time_per_div
        t1, t2 = (ln.value() * td for ln in self.view.cur_t)
        v1, v2 = ((ln.value() - ch.pos) * ch.vdiv for ln in self.view.cur_v)
        dt = abs(t2 - t1)
        inv = eng(1 / dt, "Hz") if dt > 0 else "--"
        self.cur_label.setText(f"ΔT {eng(dt, 's')}   1/ΔT {inv}\nΔV {eng(abs(v2 - v1), 'V')}\n"
                               f"V1 {eng(v1, 'V')}   V2 {eng(v2, 'V')}")

    # ---------------------------------------------------------- main refresh
    def _tick(self) -> None:
        if self.runner is None:
            return
        if self.runner.error is not None:
            err, self.runner.error = self.runner.error, None
            self.engine.stop()
            W.QMessageBox.critical(self, "Acquisition error", str(err))
        if self.writer is not None and self.writer.error is not None:
            err = self.writer.error
            self._stop_recording(report=False)
            W.QMessageBox.critical(self, "Recording error", str(err))
        fr = self.engine.update(self.runner.buffer)
        if fr is not None:
            self._frame = fr
            self.view.set_frame(fr)
            self._refresh_trace_only()
            now = time.monotonic()
            if now - self._last_measure > 0.25:
                self._last_measure = now
                self._update_measure()
        if self.engine.status != self._last_status:
            self._last_status = self.engine.status
            self.view.status.setText(self._last_status)
        run = self.engine.running
        self.run_btn.setText("RUN" if run else "STOP")
        self.run_btn.setStyleSheet("background:#1e7a2e; color:white; font-weight:bold;" if run
                                   else "background:#a02020; color:white; font-weight:bold;")

    def _refresh_trace_only(self) -> None:
        e = self.engine
        self.view.redraw(self.channels, e.time_per_div, e.trigger_pos, e.trigger.source, e.trigger.level)

    def _update_measure(self) -> None:
        fr = self._frame
        if fr is None:
            return
        v0 = fr.valid_from
        for i, ch in enumerate(self.channels):
            m = measure(fr.data[i, v0:], fr.sample_rate) if ch.enabled else {}
            for r, (_, key, unit) in enumerate(MEASURES):
                val = m.get(key, float("nan"))
                text = "--" if val != val else (f"{val * 100:.1f} %" if key == "duty" else eng(val, unit))
                self.table.setItem(r, i, W.QTableWidgetItem(text))

    # ------------------------------------------------------------ file output
    def _toggle_record(self) -> None:
        if self.writer is not None:
            self._stop_recording()
            return
        if self.runner is None:
            return
        path, _ = W.QFileDialog.getSaveFileName(self, "Record to file", "recording.h5",
                                                "HDF5 (*.h5);;CSV (*.csv);;NumPy (*.npz)")
        if not path:
            return
        try:
            self.writer = open_writer(path, self.names, self.engine.sample_rate)
        except Exception as exc:
            W.QMessageBox.critical(self, "Record", str(exc))
            return
        self.runner.subscribe(self.writer.put)
        self.rec_btn.setText("Stop rec")
        self.rec_btn.setStyleSheet("background:#a02020; color:white; font-weight:bold;")

    def _stop_recording(self, report: bool = True) -> None:
        w, self.writer = self.writer, None
        self.rec_btn.setText("Record")
        self.rec_btn.setStyleSheet("")
        if w is None:
            return
        if self.runner is not None:
            self.runner.unsubscribe(w.put)
        try:
            w.close()
            if report:
                self.statusBar().showMessage(f"Saved {w.samples_written} samples to {w.path}", 8000)
        except Exception as exc:
            if report:
                W.QMessageBox.critical(self, "Record", str(exc))

    def _save_frame(self) -> None:
        fr = self._frame
        if fr is None:
            return
        path, _ = W.QFileDialog.getSaveFileName(self, "Save frame", "frame.npz", "NumPy (*.npz);;CSV (*.csv)")
        if not path:
            return
        v0 = fr.valid_from
        t, d = fr.time[v0:], fr.data[:, v0:]
        if path.lower().endswith(".csv"):
            np.savetxt(path, np.column_stack([t, d.T]), delimiter=",", fmt="%.9g",
                       header="time_s," + ",".join(self.names), comments="")
        else:
            np.savez(path, time=t, data=d, channels=np.array(self.names), sample_rate=fr.sample_rate)

    def closeEvent(self, ev: QtGui.QCloseEvent) -> None:
        self.timer.stop()
        self._stop_recording(report=False)
        self._teardown()
        super().closeEvent(ev)
