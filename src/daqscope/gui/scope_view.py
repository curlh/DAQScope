"""The oscilloscope screen: a fixed 10 x 8 division graticule drawn in division units."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from ..core.decimate import minmax_decimate
from ..core.scope import DIVS_X, DIVS_Y, ScopeFrame
from .qt import Qt, Signal, pg

HX, HY = DIVS_X / 2, DIVS_Y / 2

COLORS = ["#f5c518", "#22d3ee", "#f472b6", "#4ade80", "#fb923c", "#a78bfa", "#f87171", "#60a5fa"]


@dataclass
class ChannelView:
    enabled: bool = True
    vdiv: float = 1.0
    pos: float = 0.0             # vertical position in divisions


class ScopeView(pg.PlotWidget):
    triggerLevelMoved = Signal(float)     # screen divisions
    cursorsMoved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, background="#05070b", antialias=True)
        self.setMenuEnabled(False)
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.plotItem.hideButtons()
        vb = self.getViewBox()
        vb.setMouseEnabled(False, False)
        vb.disableAutoRange()
        vb.setRange(xRange=(-HX, HX), yRange=(-HY, HY), padding=0)
        vb.setLimits(xMin=-HX, xMax=HX, yMin=-HY, yMax=HY)
        self.plotItem.setContentsMargins(0, 0, 0, 0)
        self._frame: Optional[ScopeFrame] = None
        self._tdiv = 1e-3
        self._traces: List[pg.PlotCurveItem] = []
        self._glows: List[pg.PlotCurveItem] = []
        self._block = False
        self._draw_graticule()

        self.ground = pg.ScatterPlotItem(symbol="t2", size=11, pen=None)
        self.ground.setZValue(5)
        self.addItem(self.ground)
        self.trig_marker = pg.ScatterPlotItem(symbol="t3", size=11, pen=None)
        self.trig_marker.setZValue(5)
        self.addItem(self.trig_marker)
        self.trig_pos_marker = pg.ScatterPlotItem(symbol="t", size=11, pen=None,
                                                  brush=pg.mkBrush("#ff9933"))
        self.trig_pos_marker.setZValue(5)
        self.addItem(self.trig_pos_marker)

        self.level_line = pg.InfiniteLine(angle=0, movable=True, bounds=(-HY, HY),
                                          pen=pg.mkPen("#ff9933", style=Qt.DashLine, width=1))
        self.level_line.setZValue(4)
        self.level_line.sigPositionChanged.connect(self._level_dragged)
        self.addItem(self.level_line)

        dash = pg.mkPen("#dddddd", style=Qt.DashLine, width=1)
        self.cur_t = [pg.InfiniteLine(pos=p, angle=90, movable=True, pen=dash, bounds=(-HX, HX)) for p in (-2, 2)]
        self.cur_v = [pg.InfiniteLine(pos=p, angle=0, movable=True, pen=dash, bounds=(-HY, HY)) for p in (-2, 2)]
        for ln in self.cur_t + self.cur_v:
            ln.setZValue(4)
            ln.setVisible(False)
            ln.sigPositionChanged.connect(lambda *_: self.cursorsMoved.emit())
            self.addItem(ln)

        self.status = pg.TextItem("", anchor=(0, 0))
        self.status.setPos(-HX + 0.12, HY - 0.08)
        self.status.setZValue(6)
        self.addItem(self.status)
        self.rate_label = pg.TextItem("", anchor=(1, 0))
        self.rate_label.setPos(HX - 0.12, HY - 0.08)
        self.rate_label.setZValue(6)
        self.addItem(self.rate_label)

    def _draw_graticule(self) -> None:
        xs, ys = [], []
        for x in range(-int(HX), int(HX) + 1):
            xs += [x, x]
            ys += [-HY, HY]
        for y in range(-int(HY), int(HY) + 1):
            xs += [-HX, HX]
            ys += [y, y]
        grid = pg.PlotCurveItem(xs, ys, connect="pairs", pen=pg.mkPen((34, 42, 58), width=1))
        grid.setZValue(0)
        self.addItem(grid)
        tx, ty = [], []
        for i in range(int(-HX * 5), int(HX * 5) + 1):          # five ticks per division
            x = i / 5
            tx += [x, x]
            ty += [-0.08, 0.08]
        for i in range(int(-HY * 5), int(HY * 5) + 1):
            y = i / 5
            tx += [-0.08, 0.08]
            ty += [y, y]
        ticks = pg.PlotCurveItem(tx, ty, connect="pairs", pen=pg.mkPen((96, 108, 132), width=1))
        ticks.setZValue(1)
        self.addItem(ticks)
        axes = pg.PlotCurveItem([-HX, HX, 0, 0], [0, 0, -HY, HY], connect=np.array([1, 0, 1, 0]),
                                pen=pg.mkPen((62, 72, 94), width=1))
        axes.setZValue(1)
        self.addItem(axes)

    def set_channel_count(self, n: int) -> None:
        for t in self._traces + self._glows:
            self.removeItem(t)
        self._traces, self._glows = [], []
        for i in range(n):
            col = pg.mkColor(COLORS[i % len(COLORS)])
            halo = pg.mkColor(col)
            halo.setAlpha(46)
            g = pg.PlotCurveItem(pen=pg.mkPen(halo, width=6))      # soft halo under the trace
            g.setZValue(2)
            t = pg.PlotCurveItem(pen=pg.mkPen(col, width=1.8))
            t.setZValue(3)
            self.addItem(g)
            self.addItem(t)
            self._glows.append(g)
            self._traces.append(t)
        self._frame = None

    def set_frame(self, frame: Optional[ScopeFrame]) -> None:
        self._frame = frame

    def clear_frame(self) -> None:
        self._frame = None
        for t in self._traces + self._glows:
            t.setData([], [])

    def redraw(self, channels: List[ChannelView], tdiv: float, trigger_pos: float,
               trig_source: int, trig_level: float) -> None:
        """Draw the stored frame with the current scales. Called after any knob change."""
        self._tdiv = tdiv
        fr = self._frame
        npx = max(2 * self.width(), 1000)
        for i, tr in enumerate(self._traces):
            if fr is None or i >= len(channels) or not channels[i].enabled or i >= fr.data.shape[0]:
                tr.setData([], [])
                self._glows[i].setData([], [])
                continue
            v0 = fr.valid_from
            t, y = minmax_decimate(fr.time[v0:], fr.data[i, v0:], npx)
            x, yy = t / tdiv, y / channels[i].vdiv + channels[i].pos
            tr.setData(x, yy)
            self._glows[i].setData(x, yy)
        xs, ys, brushes = [], [], []
        for i, ch in enumerate(channels):
            if ch.enabled:
                xs.append(-HX + 0.18)
                ys.append(ch.pos)
                brushes.append(pg.mkBrush(COLORS[i % len(COLORS)]))
        self.ground.setData(x=xs, y=ys, brush=brushes)
        self.trig_pos_marker.setData(x=[-HX + DIVS_X * trigger_pos], y=[HY - 0.2])
        if 0 <= trig_source < len(channels):
            src = channels[trig_source]
            ydiv = trig_level / src.vdiv + src.pos
            col = COLORS[trig_source % len(COLORS)]
            self.trig_marker.setData(x=[HX - 0.18], y=[ydiv], brush=[pg.mkBrush(col)])
            self._block = True
            self.level_line.setValue(ydiv)
            self._block = False

    def _level_dragged(self) -> None:
        if not self._block:
            self.triggerLevelMoved.emit(float(self.level_line.value()))

    def set_status(self, text: str, color: str, rate: str = "") -> None:
        self.status.setHtml(f"<span style='color:{color}; font-size:13px; font-weight:700'>&#9679; {text}</span>")
        self.rate_label.setHtml(f"<span style='color:#7d889c; font-size:12px'>{rate}</span>")

    def show_cursors(self, on: bool) -> None:
        for ln in self.cur_t + self.cur_v:
            ln.setVisible(on)
