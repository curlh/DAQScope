"""Oscilloscope main window.

Layout follows a bench scope. The screen is on the left with the horizontal controls and the
channel selector underneath. The panel on the right shows only the menu of the selected channel,
the trigger, and the cursor and measurement readouts once they are switched on.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

import numpy as np

from ..backends import available_backends, get_backend
from ..core import (AcquisitionSession, AIChannel, AIConfig, FrameAverager, ScopeEngine,
                    ScopeFrame, StreamRunner, TriggerConfig, measure)
from ..core.scope import DIVS_X
from ..io import open_writer
from .qt import QtCore, QtGui, QtWidgets, QTimer, Qt
from .scope_view import COLORS, ChannelView, ScopeView
from .theme import MUTED, STATUS_COLORS, repolish
from .units import ceil_125, eng, steps_125

W = QtWidgets
RATES = [1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 2.5e5]
MEASURES = [("Vpp", "pp", "V"), ("Max", "max", "V"), ("Min", "min", "V"), ("Mean", "mean", "V"),
            ("RMS", "rms", "V"), ("Frequency", "freq", "Hz"), ("Period", "period", "s"),
            ("Duty cycle", "duty", "")]
AVERAGES = (4, 16, 64)
VDIV_STEPS = steps_125(1e-3, 5.0)
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


def _label(text, role="muted"):
    lab = W.QLabel(text)
    lab.setProperty("role", role)
    return lab


def _prop(widget, name, value):
    widget.setProperty(name, value)
    repolish(widget)


def _default_offset(i: int, n: int) -> float:
    """Spread the channels over the screen at 1 V/div, in volts."""
    return ((n - 1) / 2 - i) * 1.6


class Card(W.QFrame):
    """A channel tile. Click selects the channel, the wheel steps its V/div."""
    clicked = QtCore.Signal()
    wheel = QtCore.Signal(int)

    def __init__(self, title: str, color: str):
        super().__init__()
        self.setObjectName("seg")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        self._color = color
        lay = W.QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 14, 5)
        lay.setSpacing(10)
        self.title = _label(title, "muted")
        self.value = _label("", "value")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        self.set_state(True, False)

    def set_value(self, text: str) -> None:
        self.value.setText(text)

    def set_state(self, on: bool, selected: bool) -> None:
        """On: the channel box is filled with the channel colour, like a lit key. Off: hollow grey.
        The selected channel also gets a bar on top."""
        if on:
            self.title.setStyleSheet(f"background:{self._color}; color:#000; font-weight:bold;"
                                     " font-size:13px; padding: 4px 9px;")
            self.value.setStyleSheet("")
        else:
            self.title.setStyleSheet("color:#7a7a7a; font-weight:bold; font-size:13px;"
                                     " border:1px solid #5a5a5a; padding: 3px 8px;")
            self.value.setStyleSheet("color:#6a6a6a;")
        self.setStyleSheet(f"QFrame#seg {{ border-top: 3px solid {self._color if selected else 'transparent'}; }}")

    def mousePressEvent(self, ev) -> None:
        self.clicked.emit()

    def wheelEvent(self, ev) -> None:
        self.wheel.emit(1 if ev.angleDelta().y() > 0 else -1)
        ev.accept()


class MainWindow(W.QMainWindow):
    def __init__(self, backend_name: str = "simulated"):
        super().__init__()
        self.setWindowTitle("DAQScope")
        self.resize(1480, 860)
        self.backend = get_backend(backend_name)
        self.session: Optional[AcquisitionSession] = None
        self.runner: Optional[StreamRunner] = None
        self.engine: Optional[ScopeEngine] = None
        self.writer = None
        self.names: List[str] = []
        self.channels: List[ChannelView] = []
        self.sel = 0                                  # channel shown in the channel menu
        self.meas: List[Tuple[int, str]] = []         # measurements added by the user (source, key)
        self.acq: Tuple[str, int] = ("normal", 1)     # acquire mode and its average count
        self.averager = FrameAverager()
        self._sig = None
        self._saved = {}                 # per channel name: (vdiv, offset, invert), kept across re-applies
        self._frame: Optional[ScopeFrame] = None
        self._last_measure = 0.0
        self._last_status = ""
        self._loading = False
        self.cards: List[Card] = []
        self._build_ui()
        self._build_setup_dialog()
        self._fill_backends(backend_name)
        self._fill_devices()
        self.apply_acquisition()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(20)

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        root = W.QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        body = W.QHBoxLayout(root)
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(8)

        left = W.QVBoxLayout()
        left.setSpacing(6)
        self.view = ScopeView()
        self.view.triggerLevelMoved.connect(self._level_dragged)
        self.view.cursorsMoved.connect(self._update_cursor_readout)
        self.view.wheelStepped.connect(lambda d: self._step_combo(self.tdiv_box, -d))
        frame = W.QFrame()
        frame.setObjectName("screenFrame")
        fl = W.QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self.view)
        left.addWidget(frame, 1)
        left.addWidget(self._bottom_bar())
        body.addLayout(left, 1)

        groups = W.QWidget()
        gl = W.QVBoxLayout(groups)
        gl.setContentsMargins(0, 0, 4, 0)
        gl.setSpacing(2)
        self.ch_box = W.QGroupBox("Channel 1")
        self.ch_box.setLayout(self._channel_form())
        self.trig_box = W.QGroupBox("Trigger")
        self.trig_box.setLayout(self._trigger_form())
        self.cur_box = W.QGroupBox("Cursors")
        self.cur_label = _label("", "mono")
        cl = W.QVBoxLayout(self.cur_box)
        cl.addWidget(self.cur_label)
        self.meas_box = W.QGroupBox("Measurements")
        ml = W.QVBoxLayout(self.meas_box)
        self.table = W.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Source", "Measure", "Value"])
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(W.QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(21)
        self.table.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.Stretch)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        ml.addWidget(self.table)
        for box in (self.ch_box, self.trig_box, self.cur_box, self.meas_box):
            gl.addWidget(box)
        gl.addStretch(1)
        self.cur_box.hide()
        self.meas_box.hide()
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(groups)
        scroll.setFrameShape(W.QFrame.NoFrame)
        scroll.setFixedWidth(330)
        body.addWidget(scroll)

        self.device_label = W.QLabel("")
        self.device_label.setProperty("role", "muted")
        self.statusBar().addPermanentWidget(self.device_label)
        self._toolbar()
        self._menus()

    def _bottom_bar(self) -> W.QFrame:
        """Channel selector on the left, horizontal controls on the right."""
        bar = W.QFrame()
        bar.setObjectName("bar")
        self.cards_row = W.QHBoxLayout(bar)
        self.cards_row.setContentsMargins(0, 0, 0, 0)
        self.cards_row.setSpacing(0)
        self.cards_row.addStretch(1)
        horiz = W.QHBoxLayout()
        horiz.setContentsMargins(12, 3, 8, 3)
        horiz.setSpacing(8)
        self.tdiv_box = W.QComboBox()
        self.tdiv_box.activated.connect(self._changed)
        self.tpos_spin = _spin(0, 100, 5, 0, " %")
        self.tpos_spin.setValue(50)
        self.tpos_spin.valueChanged.connect(self._changed)
        horiz.addWidget(_label("Time/div"))
        horiz.addWidget(self.tdiv_box)
        horiz.addWidget(_label("Trig pos"))
        horiz.addWidget(self.tpos_spin)
        wrap = W.QWidget()
        wrap.setLayout(horiz)
        self.cards_row.addWidget(wrap)
        return bar

    def _channel_form(self):
        f = W.QFormLayout()
        f.setVerticalSpacing(6)
        self.vbox = W.QComboBox()
        for v in VDIV_STEPS:
            self.vbox.addItem(eng(v, "V") + "/div", v)
        self.vbox.activated.connect(self._changed)
        self.offset_spin = _spin(-100, 100, 0.1, 3, " V")
        self.offset_spin.valueChanged.connect(self._changed)
        self.inv_chk = W.QCheckBox("Invert")
        self.inv_chk.toggled.connect(self._changed)
        f.addRow("Scale", self.vbox)
        f.addRow("Offset", self.offset_spin)
        f.addRow("", self.inv_chk)
        return f

    def _trigger_form(self):
        f = W.QFormLayout()
        f.setVerticalSpacing(6)
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
        self.hyst_auto = W.QCheckBox("Auto")
        self.hyst_auto.setChecked(True)
        self.hyst_auto.toggled.connect(self._changed)
        hyst_row = W.QHBoxLayout()
        hyst_row.addWidget(self.hyst_spin, 1)
        hyst_row.addWidget(self.hyst_auto)
        f.addRow("Source", self.src_box)
        f.addRow("Slope", self.slope_box)
        f.addRow("Mode", self.mode_box)
        f.addRow("Level", self.level_spin)
        f.addRow("Hysteresis", hyst_row)
        return f

    def _toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setFloatable(False)

        def button(text, slot, tip=""):
            b = W.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            tb.addWidget(b)
            return b
        self.run_btn = button("Run", self._toggle_run, "Run / Stop (F5)")
        self.single_btn = button("Single", self._single, "Single acquisition (F6)")
        self.force_btn = button("Force", self._force, "Force trigger (F7)")
        self.auto_btn = button("Autoset", self._autoset, "Autoset (F8)")
        self.default_btn = button("Default", self._default_setup, "Default setup")
        tb.addSeparator()

        self.meas_btn = W.QToolButton()
        self.meas_btn.setText("Measure")
        self.meas_btn.setPopupMode(W.QToolButton.InstantPopup)
        self.meas_menu = W.QMenu(self.meas_btn)
        self.meas_menu.aboutToShow.connect(self._build_measure_menu)
        self.meas_btn.setMenu(self.meas_menu)
        tb.addWidget(self.meas_btn)
        self.cur_btn = W.QPushButton("Cursors")
        self.cur_btn.setCheckable(True)
        self.cur_btn.toggled.connect(self._cursors_toggled)
        tb.addWidget(self.cur_btn)
        self.acq_btn = W.QToolButton()
        self.acq_btn.setText("Acquire")
        self.acq_btn.setPopupMode(W.QToolButton.InstantPopup)
        acq_menu = W.QMenu(self.acq_btn)
        group = QtGui.QActionGroup(self)
        self.acq_actions = {}
        for label, mode, n in [("Normal", "normal", 1)] + [(f"Average {k}", "average", k) for k in AVERAGES]:
            a = QtGui.QAction(label, self)
            a.setCheckable(True)
            a.setChecked(mode == "normal")
            a.triggered.connect(lambda _=False, m=mode, n=n: self._set_acq(m, n))
            group.addAction(a)
            acq_menu.addAction(a)
            self.acq_actions[(mode, n)] = a
        self.acq_btn.setMenu(acq_menu)
        tb.addWidget(self.acq_btn)
        button("Clear", self._clear_display, "Clear display and averages")
        tb.addSeparator()
        self.rec_btn = button("Record", self._toggle_record, "Record to file (Ctrl+R)")
        self.save_btn = button("Save frame", self._save_frame, "Save the frame on screen (Ctrl+S)")
        self.setup_btn = button("Setup...", self._show_setup, "Device, inputs and sample rate")

        for key, slot in (("F5", self._toggle_run), ("F6", self._single), ("F7", self._force),
                          ("F8", self._autoset), ("Ctrl+R", self._toggle_record),
                          ("Ctrl+S", self._save_frame)):
            sc = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            sc.activated.connect(slot)

    def _menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for text, slot in (("Record...", self._toggle_record), ("Save frame...", self._save_frame),
                           ("Setup...", self._show_setup)):
            a = QtGui.QAction(text, self)
            a.triggered.connect(slot)
            m.addAction(a)
        m.addSeparator()
        q = QtGui.QAction("Quit", self)
        q.triggered.connect(self.close)
        m.addAction(q)
        m = mb.addMenu("&Help")
        a = QtGui.QAction("About", self)
        a.triggered.connect(lambda: W.QMessageBox.about(
            self, "About DAQScope", "DAQScope\nOscilloscope front end for DAQ devices.\n"
            "Not affiliated with National Instruments."))
        m.addAction(a)

    def _build_setup_dialog(self) -> None:
        """Device, inputs and sample rate. Rarely changed, so it lives in a dialog."""
        self.setup = W.QDialog(self)
        self.setup.setWindowTitle("Acquisition setup")
        f = W.QFormLayout(self.setup)
        f.setVerticalSpacing(8)
        self.backend_box = W.QComboBox()
        self.backend_box.activated.connect(self._backend_changed)
        self.device_box = W.QComboBox()
        self.device_box.activated.connect(lambda *_: self._fill_channels())
        self.chan_list = W.QListWidget()
        self.chan_list.setMinimumHeight(150)
        self.chan_list.itemChanged.connect(lambda *_: self._fill_rates())
        self.rate_box = W.QComboBox()
        apply = W.QPushButton("Apply")
        apply.clicked.connect(self._apply_clicked)
        f.addRow("Backend", self.backend_box)
        f.addRow("Device", self.device_box)
        f.addRow("Inputs", self.chan_list)
        f.addRow("Sample rate", self.rate_box)
        f.addRow(apply)
        self.setup.setMinimumWidth(420)

    def _show_setup(self) -> None:
        self.setup.show()
        self.setup.raise_()

    def _apply_clicked(self) -> None:
        self.apply_acquisition()
        self.setup.hide()

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
            self._saved[nm] = (ch.vdiv, ch.offset, ch.invert)
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
            vdiv, offset, inv = self._saved.get(nm, (1.0, _default_offset(i, n), False))
            self.channels.append(ChannelView(True, vdiv, offset, inv))
        self.meas = [(s, k) for s, k in self.meas if s < n]
        self.sel = min(self.sel, n - 1)
        self.view.set_channel_count(n)
        self._frame = None
        self._reset_average()
        self._build_cards()
        self._fill_timebase()
        self._loading = True
        self.src_box.clear()
        self.src_box.addItems([f"CH{i + 1}  {nm.split('/')[-1]}" for i, nm in enumerate(names)])
        self._loading = False
        self._select_channel(self.sel)
        self.engine.run(self.runner.buffer)
        self._changed()
        self._rebuild_table()
        dev = self.device_box.currentData()
        self.device_label.setText(f"{self.backend.name}  {dev.name} {dev.product_type}".strip() if dev
                                  else self.backend.name)

    def _build_cards(self) -> None:
        for c in self.cards:
            self.cards_row.removeWidget(c)
            c.deleteLater()
        self.cards = []
        for i in range(len(self.names)):
            c = Card(f"CH{i + 1}", COLORS[i % len(COLORS)])
            c.clicked.connect(lambda i=i: self._channel_key(i))
            c.wheel.connect(lambda d, i=i: self._step_vdiv(i, -d))
            self.cards_row.insertWidget(i, c)
            self.cards.append(c)

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
    def _select_channel(self, i: int) -> None:
        self.sel = i
        ch = self.channels[i]
        col = COLORS[i % len(COLORS)]
        self.ch_box.setTitle(f"Channel {i + 1}")
        self.ch_box.setStyleSheet(f"QGroupBox::title {{ color: {col}; }}")
        for w in (self.vbox, self.offset_spin, self.inv_chk):
            w.blockSignals(True)
        self.vbox.setCurrentIndex(max(0, self.vbox.findData(ch.vdiv)))
        self.offset_spin.setSingleStep(ch.vdiv / 10)
        self.offset_spin.setValue(ch.offset)
        self.inv_chk.setChecked(ch.invert)
        for w in (self.vbox, self.offset_spin, self.inv_chk):
            w.blockSignals(False)
        for k, (c, cv) in enumerate(zip(self.cards, self.channels)):
            c.set_state(cv.enabled, k == i)
        self._update_cursor_readout()

    def _channel_key(self, i: int) -> None:
        """Channel key: off -> on and selected, on -> selected, selected -> off."""
        ch = self.channels[i]
        if not ch.enabled:
            ch.enabled = True
            self._select_channel(i)
        elif i != self.sel:
            self._select_channel(i)
        else:
            ch.enabled = False
            self._select_channel(i)
        self._refresh()

    def _step_combo(self, box: W.QComboBox, step: int) -> None:
        """Move a 1-2-5 combo by one step, as turning a knob."""
        i = min(max(box.currentIndex() + step, 0), box.count() - 1)
        if i != box.currentIndex():
            box.setCurrentIndex(i)
            self._changed()

    def _step_vdiv(self, i: int, step: int) -> None:
        ch = self.channels[i]
        k = min(max(VDIV_STEPS.index(min(VDIV_STEPS, key=lambda v: abs(v - ch.vdiv))) + step, 0),
                len(VDIV_STEPS) - 1)
        ch.vdiv = VDIV_STEPS[k]
        if i == self.sel:
            self._select_channel(i)
        self._changed()

    def _changed(self, *_) -> None:
        """Read the widgets into the channel, timebase and trigger settings."""
        if self._loading or self.engine is None:
            return
        ch = self.channels[self.sel]
        ch.vdiv = self.vbox.currentData()
        ch.offset = self.offset_spin.value()
        ch.invert = self.inv_chk.isChecked()
        e = self.engine
        e.time_per_div = self.tdiv_box.currentData()
        e.trigger_pos = self.tpos_spin.value() / 100
        src = max(0, self.src_box.currentIndex())
        e.trigger = TriggerConfig(src, self.level_spin.value(),
                                  self.slope_box.currentText().lower(),
                                  self.mode_box.currentText().lower(),
                                  None if self.hyst_auto.isChecked() else self.hyst_spin.value())
        self.hyst_spin.setEnabled(not self.hyst_auto.isChecked())
        step = self.channels[src].vdiv / 10
        self.level_spin.setSingleStep(step)
        self.hyst_spin.setSingleStep(step)
        sig = (e.time_per_div, e.trigger_pos, e.trigger)
        if sig != self._sig:               # averages are only valid for one timebase and trigger
            self._sig = sig
            self._reset_average()
        self._refresh()

    def _refresh(self) -> None:
        e = self.engine
        self.view.redraw(self.channels, e.time_per_div, e.trigger_pos, e.trigger.source, e.trigger.level)
        for k, (card, ch) in enumerate(zip(self.cards, self.channels)):
            card.set_value(f"{eng(ch.vdiv, 'V')}/div" + (" inv" if ch.invert else ""))
            card.set_state(ch.enabled, k == self.sel)
        self._overlay()
        self._update_cursor_readout()

    def _overlay(self) -> None:
        """Status and acquisition info drawn in the corners of the screen."""
        if self.engine is None:
            return
        status = self.engine.status
        mode, n = self.acq
        info = eng(self.engine.sample_rate, "S/s") + (f"   Average {n}" if mode == "average" else "")
        self.view.set_status(status, STATUS_COLORS.get(status, MUTED), info)

    def _level_dragged(self, ydiv: float) -> None:
        if self.engine is None:
            return
        ch = self.channels[self.engine.trigger.source]
        self.level_spin.setValue(ydiv * ch.vdiv - ch.offset)      # valueChanged runs _changed

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

    def _force(self) -> None:
        if self.engine is None:
            return
        fr = self.engine.force(self.runner.buffer)
        if fr is not None:
            self._show(fr)

    def _clear_display(self) -> None:
        self._frame = None
        self._reset_average()
        self.view.clear_frame()
        self._update_measure()

    def _default_setup(self) -> None:
        """Back to the power-on state: all channels shown, 1 V/div, auto trigger at 0 V."""
        self._stop_recording()
        self._saved.clear()
        self.channels, self.names = [], []        # so apply_acquisition does not save the old scales
        self.meas.clear()
        self.cur_btn.setChecked(False)
        self._set_acq("normal", 1)
        self.acq_actions[("normal", 1)].setChecked(True)
        self._loading = True
        self.tpos_spin.setValue(50)
        self.slope_box.setCurrentIndex(0)
        self.mode_box.setCurrentIndex(0)
        self.level_spin.setValue(0.0)
        self.hyst_auto.setChecked(True)
        self.tdiv_box.setCurrentIndex(max(0, self.tdiv_box.findData(2e-2)))
        self._loading = False
        self.sel = 0
        self.apply_acquisition()

    def _autoset(self) -> None:
        if self.engine is None or self.runner is None:
            return
        fs = self.engine.sample_rate
        data = self.runner.buffer.latest(int(fs * 0.5))
        if data.shape[1] < 100:
            return
        src = max(0, self.src_box.currentIndex())
        self._loading = True
        for i, ch in enumerate(self.channels):
            if not ch.enabled:
                continue
            m = measure(data[i], fs)
            if not np.isfinite(m["pp"]):
                continue
            ch.vdiv = min(5.0, max(1e-3, ceil_125(max(m["pp"], 1e-6) / 6)))    # signal fills 6 of 8 divisions
            ch.offset = -(m["max"] + m["min"]) / 2                 # centre the signal
            if i == src:
                self.level_spin.setValue((m["max"] + m["min"]) / 2)
                if np.isfinite(m["freq"]):
                    want = 3 / m["freq"] / DIVS_X                          # three cycles on screen
                    j = min(range(self.tdiv_box.count()),
                            key=lambda k: abs(np.log(self.tdiv_box.itemData(k) / want)))
                    self.tdiv_box.setCurrentIndex(j)
        self.mode_box.setCurrentText("Auto")
        self.tpos_spin.setValue(50)
        self._loading = False
        self._select_channel(self.sel)
        self._changed()
        self.engine.run(self.runner.buffer)

    # ------------------------------------------------------------- acquire
    def _set_acq(self, mode: str, n: int) -> None:
        self.acq = (mode, n)
        self.averager.reset(n if mode == "average" else 1)
        self._overlay()

    def _reset_average(self) -> None:
        self.averager.reset()

    def _show(self, fr: ScopeFrame) -> None:
        fr = self.averager.add(fr)
        self._frame = fr
        self.view.set_frame(fr)
        e = self.engine
        self.view.redraw(self.channels, e.time_per_div, e.trigger_pos, e.trigger.source, e.trigger.level)
        now = time.monotonic()
        if now - self._last_measure > 0.25:
            self._last_measure = now
            self._update_measure()

    # --------------------------------------------------------------- cursors
    def _cursors_toggled(self, on: bool) -> None:
        self.view.show_cursors(on)
        self.cur_box.setVisible(on)
        self._update_cursor_readout()

    def _update_cursor_readout(self, *_) -> None:
        if not self.cur_btn.isChecked() or self.engine is None or not self.channels:
            return
        ch = self.channels[self.sel]
        td = self.engine.time_per_div
        t1, t2 = (ln.value() * td for ln in self.view.cur_t)
        v1, v2 = (ln.value() * ch.vdiv - ch.offset for ln in self.view.cur_v)
        dt = abs(t2 - t1)
        inv = eng(1 / dt, "Hz") if dt > 0 else "--"
        self.cur_label.setText(f"Source  CH{self.sel + 1}\nΔT      {eng(dt, 's')}\n1/ΔT    {inv}\n"
                               f"ΔV      {eng(abs(v2 - v1), 'V')}\nV1      {eng(v1, 'V')}\n"
                               f"V2      {eng(v2, 'V')}")

    # ----------------------------------------------------------- measurements
    def _build_measure_menu(self) -> None:
        m = self.meas_menu
        m.clear()
        head = m.addAction(f"Source: CH{self.sel + 1}")
        head.setEnabled(False)
        m.addSeparator()
        for label, key, _ in MEASURES:
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked((self.sel, key) in self.meas)
            a.triggered.connect(lambda _=False, k=key: self._toggle_measure(self.sel, k))
        m.addSeparator()
        m.addAction("Clear all").triggered.connect(self._clear_measures)

    def _toggle_measure(self, src: int, key: str) -> None:
        if (src, key) in self.meas:
            self.meas.remove((src, key))
        else:
            self.meas.append((src, key))
        self._rebuild_table()

    def _clear_measures(self) -> None:
        self.meas.clear()
        self._rebuild_table()

    def _table_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if 0 <= row < len(self.meas):
            menu = W.QMenu(self)
            menu.addAction("Remove").triggered.connect(lambda: self._remove_measure(row))
            menu.exec(self.table.viewport().mapToGlobal(pos))

    def _remove_measure(self, row: int) -> None:
        del self.meas[row]
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        names = {k: (label, unit) for label, k, unit in MEASURES}
        self.table.setRowCount(len(self.meas))
        for r, (src, key) in enumerate(self.meas):
            s = W.QTableWidgetItem(f"CH{src + 1}")
            s.setForeground(QtGui.QColor(COLORS[src % len(COLORS)]))
            self.table.setItem(r, 0, s)
            self.table.setItem(r, 1, W.QTableWidgetItem(names[key][0]))
        self.meas_box.setVisible(bool(self.meas))
        self.table.setFixedHeight(self.table.horizontalHeader().height() + 21 * len(self.meas) + 4)
        self._update_measure()

    def _update_measure(self) -> None:
        fr = self._frame
        if not self.meas or fr is None:
            for r in range(len(self.meas)):
                self.table.setItem(r, 2, W.QTableWidgetItem("--"))
            return
        v0 = fr.valid_from
        cache = {}
        for r, (src, key) in enumerate(self.meas):
            if src not in cache:
                sign = -1.0 if self.channels[src].invert else 1.0
                cache[src] = measure(sign * fr.data[src, v0:], fr.sample_rate)
            val = cache[src][key]
            unit = next(u for _, k, u in MEASURES if k == key)
            text = "--" if val != val else (f"{val * 100:.1f} %" if key == "duty" else eng(val, unit))
            item = W.QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 2, item)

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
            self._show(fr)
        if self.engine.status != self._last_status:
            self._last_status = self.engine.status
            self._overlay()
        if self.hyst_auto.isChecked() and abs(self.hyst_spin.value() - self.engine.hysteresis_used) > 5e-5:
            self.hyst_spin.blockSignals(True)      # show the value the search used, without re-entering _changed
            self.hyst_spin.setValue(self.engine.hysteresis_used)
            self.hyst_spin.blockSignals(False)
        run = self.engine.running
        want = "run" if run else "stop"
        if self.run_btn.property("kind") != want:
            self.run_btn.setText("Run" if run else "Stop")
            _prop(self.run_btn, "kind", want)

    # ------------------------------------------------------------ file output
    def _toggle_record(self) -> None:
        if self.writer is not None:
            self._stop_recording()
            return
        if self.runner is None:
            return
        path, _ = W.QFileDialog.getSaveFileName(self, "Record to file", "recording.csv",
                                                "CSV (*.csv);;NumPy (*.npz)")
        if not path:
            return
        try:
            self.writer = open_writer(path, self.names, self.engine.sample_rate)
        except Exception as exc:
            W.QMessageBox.critical(self, "Record", str(exc))
            return
        self.runner.subscribe(self.writer.put)
        self.rec_btn.setText("Stop recording")
        _prop(self.rec_btn, "kind", "rec")

    def _stop_recording(self, report: bool = True) -> None:
        w, self.writer = self.writer, None
        self.rec_btn.setText("Record")
        _prop(self.rec_btn, "kind", "")
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
        path, _ = W.QFileDialog.getSaveFileName(self, "Save frame", "frame.csv", "CSV (*.csv);;NumPy (*.npz)")
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
