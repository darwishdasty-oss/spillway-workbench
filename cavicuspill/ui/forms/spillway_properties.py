"""
ui/forms/spillway_properties.py - Port of SpillWayProperties.frm

The original VB6 form:
  - Reads the G-Q curves precomputed by SpillWayData
  - Displays a single G-Q curve for the selected spillway length,
    via the OutflowDiagramFrm + MSChart 2.0 control
  - In the original, this is a "view-only" dialog driven by the
    active spillway length

This PySide6 port:
  - Reads the G-Q curves from APP_STATE (set by SpillwayData)
  - Lets the user pick a candidate length from a dropdown
  - Shows the G-Q curve in an embedded matplotlib chart
  - "View all lengths" toggle overlays all candidate curves

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations
import os, sys

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cavicuspill as cav  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mdi_main as _mdi_main  # noqa: E402
APP_STATE = _mdi_main.APP_STATE
from charts.matplotlib_widget import MplCanvas  # noqa: E402


class SpillwayPropertiesDialog(QtWidgets.QMdiSubWindow):
    """Port of SpillWayProperties.frm (the G-Q curve viewer)."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Spillway Properties (G-Q curves)")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(720, 560)
        self._L_data_cache: list = []  # list of (L, Q, G) tuples

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Spillway Properties &mdash; "
            "Storage&ndash;discharge (G&ndash;Q) curves</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "G = 2&middot;S/&Delta;t + Q, plotted for the candidate spillway "
            "lengths precomputed by Spillway Data. Q is the spillway discharge "
            "(L&middot;C&middot;(h &minus; E)<sup>1.5</sup>). "
            "Toggle &lsquo;Overlay all lengths&rsquo; to compare."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Controls row -----
        ctrl = QtWidgets.QHBoxLayout()
        ctrl.addWidget(QtWidgets.QLabel("Spillway length L:"))
        self.combo_L = QtWidgets.QComboBox()
        self.combo_L.setMinimumWidth(120)
        ctrl.addWidget(self.combo_L)
        self.chk_overlay = QtWidgets.QCheckBox("Overlay all lengths")
        self.chk_overlay.toggled.connect(self._redraw)
        ctrl.addWidget(self.chk_overlay)
        ctrl.addStretch(1)
        v.addLayout(ctrl)

        # ----- Chart -----
        self.canvas = MplCanvas(6.5, 4.0, dpi=100)
        v.addWidget(self.canvas, 1)

        # ----- Status line -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

        # ----- Bottom row -----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        # Populate the combo box and draw the initial chart
        self._load_data()
        self.combo_L.currentIndexChanged.connect(self._redraw)
        self._redraw()

    def _load_data(self):
        if APP_STATE.reservoir_data is None or APP_STATE.spillway_cfg is None:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Please enter Reservoir Properties "
                "and Spillway Data first.</span>")
            self.canvas.fig.clear()
            ax = self.canvas.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No G-Q curves available.\n"
                              "Enter Reservoir + Spillway Data first.",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=11, color="#888")
            ax.set_axis_off()
            self.canvas.draw()
            return
        self._L_data_cache = cav.precompute_gq_curves(
            APP_STATE.reservoir_data, APP_STATE.spillway_cfg)
        self.combo_L.blockSignals(True)
        self.combo_L.clear()
        for L, _, _ in self._L_data_cache:
            self.combo_L.addItem(f"L = {L:g} m", L)
        self.combo_L.blockSignals(False)

    def _redraw(self):
        if not self._L_data_cache:
            return
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        if self.chk_overlay.isChecked():
            cmap = plt_cm()
            for i, (L, Q, G) in enumerate(self._L_data_cache):
                color = cmap(i / max(1, len(self._L_data_cache) - 1))
                ax.plot(Q, G, color=color, lw=1.6, label=f"L = {L:g} m")
            ax.legend(fontsize=9, loc="upper left", framealpha=0.85)
        else:
            i = self.combo_L.currentIndex()
            if i < 0:
                i = 0
            L, Q, G = self._L_data_cache[i]
            ax.plot(Q, G, color="#1A3A6C", lw=2.0)
            ax.fill_between(Q, 0, G, color="#1A3A6C", alpha=0.08)
            # Annotate the peak
            i_peak = int(np.argmax(Q))
            ax.annotate(f"Q_max = {Q[i_peak]:.0f} m³/s",
                        xy=(Q[i_peak], G[i_peak]),
                        xytext=(10, -20), textcoords="offset points",
                        fontsize=10, color="#B8500A",
                        arrowprops=dict(arrowstyle="->", color="#B8500A"))
        ax.set_xlabel("Outflow discharge  Q  (m³/s)", fontsize=10)
        ax.set_ylabel("2S/Δt + Q   (m³/s)", fontsize=10)
        ax.set_title(f"Storage–discharge (G–Q) curve, L = {self._L_data_cache[self.combo_L.currentIndex()][0]:g} m",
                     fontsize=11)
        ax.grid(alpha=0.3)
        self.canvas.draw()
        L, Q, G = self._L_data_cache[max(0, self.combo_L.currentIndex())]
        self.lbl_status.setText(
            f"L = {L:g} m,  Q_max = {Q.max():.1f} m³/s,  G_max = {G.max():.1f} m³/s.")


def plt_cm():
    """Tiny wrapper to avoid an extra import in this file."""
    import matplotlib.cm as cm
    return cm.viridis
