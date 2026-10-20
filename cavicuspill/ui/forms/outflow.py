"""
ui/forms/outflow.py - Port of Outflow.frm + OutflowDiagram.frm

The original VB6 Outflow.frm has:
  - A ComboBox of candidate spillway lengths
  - Two OptionButtons: "Outflow-Inflow curve" or "(G-Q) curve"
  - OK / Cancel buttons
  - On OK, if "G-Q": calls OutflowDiagramFrm.showDiagram(True, ...)
                  if "Outflow-Inflow": calls calc_JXMO + showDiagram(False, ...)

The OutflowDiagram.frm is the MSChart 2.0 control that displays the
selected curve.

This PySide6 port:
  - Replaces the ComboBox with a QComboBox populated from APP_STATE.spillway_cfg
  - Replaces the OptionButtons with a QComboBox of two options
  - On OK, runs cav.pulse_method_routing (or uses precomputed G-Q) and
    shows the result in an embedded matplotlib chart
  - Updates APP_STATE.outflow = True

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations
import os, sys

import numpy as np
from matplotlib.ticker import MaxNLocator
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cavicuspill as cav  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mdi_main as _mdi_main  # noqa: E402
APP_STATE = _mdi_main.APP_STATE
from charts.matplotlib_widget import MplCanvas  # noqa: E402


class OutflowDialog(QtWidgets.QMdiSubWindow):
    """Port of Outflow.frm + OutflowDiagram.frm."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Outflow (Pulse-Method flood routing)")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 620)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Outflow &mdash; "
            "Pulse-Method flood routing</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Pick a candidate spillway length, pick a curve type, and click "
            "<b>OK</b> to run the routing and render the chart. The Pulse-Method "
            "algorithm is a 1:1 port of <code>Outflow.frm.calc_JXMO</code> in "
            "the original VB6 source."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Controls row -----
        ctrl = QtWidgets.QGridLayout()
        ctrl.setHorizontalSpacing(8)
        ctrl.setVerticalSpacing(6)

        # L
        ctrl.addWidget(QtWidgets.QLabel("L  (Spillway length)"), 0, 0)
        self.combo_L = QtWidgets.QComboBox()
        self.combo_L.setMinimumWidth(120)
        ctrl.addWidget(self.combo_L, 0, 1)
        # Curve type
        ctrl.addWidget(QtWidgets.QLabel("Curve type"), 0, 2)
        self.combo_curve = QtWidgets.QComboBox()
        self.combo_curve.addItems([
            "Outflow-Inflow hydrograph",
            "G-Q curve (storage-discharge)"])
        ctrl.addWidget(self.combo_curve, 0, 3)

        # OK / Cancel
        self.btn_ok = QtWidgets.QPushButton("&OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.on_ok)
        ctrl.addWidget(self.btn_ok, 0, 4)
        self.btn_cancel = QtWidgets.QPushButton("&Cancel")
        self.btn_cancel.clicked.connect(self.close)
        ctrl.addWidget(self.btn_cancel, 0, 5)

        v.addLayout(ctrl)

        # ----- Chart -----
        self.canvas = MplCanvas(7.0, 4.0, dpi=100)
        v.addWidget(self.canvas, 1)

        # ----- Status line -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

        # ----- Populate the L combo -----
        self._L_data_cache: list = []
        if APP_STATE.reservoir_data is not None and APP_STATE.spillway_cfg is not None:
            self._L_data_cache = cav.precompute_gq_curves(
                APP_STATE.reservoir_data, APP_STATE.spillway_cfg)
            for L, _, _ in self._L_data_cache:
                self.combo_L.addItem(f"L = {L:g} m", L)
            if self.combo_L.count() > 0:
                self.combo_L.setCurrentIndex(0)
            self._redraw()
        else:
            self.canvas.fig.clear()
            ax = self.canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5,
                    "Reservoir + Spillway Data must be entered first.",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=11, color="#888")
            ax.set_axis_off()
            self.canvas.draw()
            self.lbl_status.setText(
                "<span style='color:#B8500A'>"
                "Please enter Reservoir Properties and Spillway Data first.</span>")

        # Re-draw on any control change
        self.combo_L.currentIndexChanged.connect(self._redraw)
        self.combo_curve.currentIndexChanged.connect(self._redraw)

    # ------------------------------------------------------------------
    def _redraw(self):
        if not self._L_data_cache:
            return
        i = self.combo_L.currentIndex()
        if i < 0:
            return
        L, Q, G = self._L_data_cache[i]
        inflow = APP_STATE.inflow

        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)

        if self.combo_curve.currentIndex() == 0 and inflow is not None:
            # Outflow-Inflow hydrograph
            JX, MO = cav.pulse_method_routing(inflow, (L, Q, G))
            ax.plot(inflow.t_h, inflow.Q, color="#1A3A6C", lw=2.0,
                    label="Inflow (input)")
            ax.plot(inflow.t_h, MO, color="#B8500A", lw=2.0,
                    label=f"Outflow (routed) for L = {L:g} m")
            # Annotate the peak outflow
            i_peak = int(MO.argmax())
            ax.annotate(f"Q_peak = {MO[i_peak]:.1f} m³/s at t = {inflow.t_h[i_peak]:g} h",
                        xy=(inflow.t_h[i_peak], MO[i_peak]),
                        xytext=(10, -25), textcoords="offset points",
                        fontsize=10, color="#B8500A",
                        arrowprops=dict(arrowstyle="->", color="#B8500A"))
            ax.set_xlabel("Time  (h)", fontsize=10)
            ax.set_ylabel("Discharge  (m³/s)", fontsize=10)
            ax.set_title(
                f"Outflow-Inflow hydrograph  \u2014  L = {L:g} m  \u2014  "
                f"peak out = {MO[i_peak]:.1f} m³/s",
                fontsize=11)
            ax.legend(fontsize=9, loc="upper right")
            ax.grid(alpha=0.3)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            self.lbl_status.setText(
                f"L = {L:g} m,  peak out = {MO[i_peak]:.1f} m³/s at t = {inflow.t_h[i_peak]:g} h,  "
                f"time to peak = {inflow.t_h[i_peak]:g} h.")
        else:
            # G-Q curve
            ax.plot(Q, G, color="#1A3A6C", lw=2.0)
            ax.fill_between(Q, 0, G, color="#1A3A6C", alpha=0.08)
            i_peak = int(np.argmax(Q))
            ax.annotate(f"Q_max = {Q[i_peak]:.0f} m³/s",
                        xy=(Q[i_peak], G[i_peak]),
                        xytext=(10, -25), textcoords="offset points",
                        fontsize=10, color="#B8500A",
                        arrowprops=dict(arrowstyle="->", color="#B8500A"))
            ax.set_xlabel("Outflow discharge  Q  (m³/s)", fontsize=10)
            ax.set_ylabel("2S/Δt + Q   (m³/s)", fontsize=10)
            ax.set_title(
                f"Storage\u2013discharge (G\u2013Q) curve  \u2014  L = {L:g} m  \u2014  "
                f"Q_max = {Q[i_peak]:.0f} m³/s",
                fontsize=11)
            ax.grid(alpha=0.3)
            self.lbl_status.setText(
                f"L = {L:g} m,  Q_max = {Q[i_peak]:.1f} m³/s,  G_max = {G.max():.1f} m³/s.")
        self.canvas.draw()

    def on_ok(self):
        # Mark Outflow state and close
        APP_STATE.outflow = True
        self.lbl_status.setText(
            self.lbl_status.text() + "  \u2713 Pulse-Method routing committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)
