"""
ui/forms/spillway_profile.py - Port of SpillWayProfile.frm

The original VB6 SpillWayProfile.frm has:
  - Four OptionButtons for the WES standard upstream-face slopes:
    3V:0H, 3V:1H, 3V:2H, 3V:3H
  - Four PictureBox preview images (one per slope)
  - OK / Cancel buttons
  - On OK, sets appState.SpillwayProfile = True and enables
    CavicuspillFrm.ShowSpillwayProfile menu item

This PySide6 port:
  - Replaces the 4 OptionButtons with 4 radio buttons in a grid
  - Replaces the PictureBox previews with inline matplotlib drawings of
    the WES crest shape (K, P coefficients) for each slope
  - On OK, sets APP_STATE.spillwayProfile = True and stores the chosen
    slope so downstream forms (cavitation, air entrainment) know which
    design to use

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


class SpillwayProfileDialog(QtWidgets.QMdiSubWindow):
    """Port of SpillWayProfile.frm (WES design)."""

    SLOPES = [
        ("3V:0H", "3 V : 0 H  (vertical)"),
        ("3V:1H", "3 V : 1 H"),
        ("3V:2H", "3 V : 2 H"),
        ("3V:3H", "3 V : 3 H"),
    ]

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Spillway Profile (WES standard overflow)")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 560)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Spillway Profile &mdash; "
            "WES standard overflow</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "The downstream face of a WES standard overflow spillway follows "
            "y/H<sub>d</sub> = &minus;K&middot;(x/H<sub>d</sub>)<sup>P</sup>. "
            "Pick one of the four standard upstream-face slopes (3V:0H, 3V:1H, "
            "3V:2H, 3V:3H). The K, P coefficients are drawn from the USBR "
            "Design of Small Dams (1987) tables."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Q_d input row -----
        ctrl = QtWidgets.QHBoxLayout()
        ctrl.addWidget(QtWidgets.QLabel("Design discharge Q<sub>d</sub>:"))
        self.txt_Qd = QtWidgets.QLineEdit("2000")
        self.txt_Qd.setMaximumWidth(120)
        ctrl.addWidget(self.txt_Qd)
        ctrl.addWidget(QtWidgets.QLabel("<span style='color:#888'>m³/s</span>"))
        ctrl.addSpacing(16)
        ctrl.addWidget(QtWidgets.QLabel("Effective length L:"))
        self.txt_L = QtWidgets.QLineEdit("75")
        self.txt_L.setMaximumWidth(120)
        ctrl.addWidget(self.txt_L)
        ctrl.addWidget(QtWidgets.QLabel("<span style='color:#888'>m</span>"))
        ctrl.addSpacing(16)
        ctrl.addWidget(QtWidgets.QLabel("C:"))
        self.txt_C = QtWidgets.QLineEdit("2.225")
        self.txt_C.setMaximumWidth(120)
        ctrl.addWidget(self.txt_C)
        ctrl.addStretch(1)
        v.addLayout(ctrl)

        # ----- 4 slope selectors in a 2x2 grid -----
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.radios: dict = {}
        self.preview_canvases: dict = {}
        for i, (slope, label) in enumerate(self.SLOPES):
            row, col = i // 2, i % 2
            cell = QtWidgets.QGroupBox()
            cell_v = QtWidgets.QVBoxLayout(cell)
            cell_v.setContentsMargins(6, 4, 6, 4)
            cell_v.setSpacing(4)
            rb = QtWidgets.QRadioButton(label)
            self.radios[slope] = rb
            cell_v.addWidget(rb)
            # Preview canvas
            prev = MplCanvas(2.2, 1.2, dpi=80)
            cell_v.addWidget(prev)
            self.preview_canvases[slope] = prev
            grid.addWidget(cell, row, col)
        self.radios["3V:0H"].setChecked(True)
        for slope in self.radios:
            self.radios[slope].toggled.connect(self._redraw)
        v.addLayout(grid)

        # ----- Big chart (the WES crest shape) -----
        self.canvas = MplCanvas(7.0, 2.6, dpi=100)
        v.addWidget(self.canvas, 1)

        # ----- Status -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

        # ----- OK / Cancel -----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QtWidgets.QPushButton("&Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_ok = QtWidgets.QPushButton("&OK")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.on_ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        v.addLayout(btn_row)

        # Pre-populate from state
        if APP_STATE.wes_design is not None:
            d = APP_STATE.wes_design
            self.txt_Qd.setText(f"{d['Q_d']:g}")
            self.txt_L.setText(f"{d['L']:g}")
            self.txt_C.setText(f"{d['c']:g}")
            if d.get("upstream_slope") in self.radios:
                self.radios[d["upstream_slope"]].setChecked(True)

        # Initial draw
        for slope in self.preview_canvases:
            self._draw_preview(slope)
        self._redraw()

    def _selected_slope(self) -> str:
        for slope, rb in self.radios.items():
            if rb.isChecked():
                return slope
        return "3V:0H"

    def _draw_preview(self, slope: str):
        """Draw a small WES crest thumbnail for one slope."""
        K, P = cav.WES_KP_TABLE[slope]
        prev = self.preview_canvases[slope]
        prev.fig.clear()
        ax = prev.fig.add_subplot(111)
        x = np.linspace(0, 1.5, 100)
        y = -K * x ** P
        ax.plot(x, y, color="#1A3A6C", lw=2.0)
        ax.set_xlim(0, 1.5); ax.set_ylim(-1.2, 0.05)
        ax.set_aspect("equal")
        ax.set_title(f"K = {K}, P = {P}", fontsize=9)
        ax.grid(alpha=0.3)
        ax.set_xticks([]); ax.set_yticks([])
        prev.draw()

    def _redraw(self):
        slope = self._selected_slope()
        # Refresh all 4 previews (the selected one is highlighted)
        for s in self.preview_canvases:
            self._draw_preview(s)
            if s != slope:
                self.preview_canvases[s].figure.set_facecolor("#f0f0f0")
            else:
                self.preview_canvases[s].figure.set_facecolor("#FFF8DC")

        # Big chart: the WES crest shape for the selected slope
        K, P = cav.WES_KP_TABLE[slope]
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        x = np.linspace(0, 1.5, 200)
        y = -K * x ** P
        ax.plot(x, y, color="#1A3A6C", lw=2.5,
                label=f"{slope}  (K = {K}, P = {P})")
        # Mark the toe radius
        ax.axvline(1.0, color="#888", ls=":", lw=0.8)
        ax.text(1.0, 0.02, " x = H_d", fontsize=8, color="#888", ha="center")
        # Mark the crest
        ax.scatter([0], [0], color="#B8500A", s=60, zorder=5)
        ax.annotate("crest (0, 0)", xy=(0, 0), xytext=(10, 8),
                    textcoords="offset points", fontsize=9, color="#B8500A")
        ax.set_xlim(0, 1.5); ax.set_ylim(-1.2, 0.2)
        ax.set_xlabel("x / H_d", fontsize=10)
        ax.set_ylabel("y / H_d", fontsize=10)
        ax.set_title(f"WES standard overflow crest shape  \u2014  upstream slope = {slope}",
                     fontsize=11)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="lower left")
        self.canvas.draw()
        self.lbl_status.setText(
            f"Selected slope: <b>{slope}</b>  \u2014  K = {K}, P = {P}.  "
            f"Click <b>OK</b> to commit the design to APP_STATE.")

    def on_ok(self):
        try:
            Q_d = float(self.txt_Qd.text())
            L   = float(self.txt_L.text())
            c   = float(self.txt_C.text())
        except ValueError:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: Q_d, L, C must be numeric</span>")
            return
        if Q_d <= 0 or L <= 0 or c <= 0:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: Q_d, L, C must be positive</span>")
            return
        slope = self._selected_slope()
        design = cav.wes_design(Q_d=Q_d, L=L, c=c, upstream_slope=slope)
        design["Q_d"] = Q_d
        design["L"] = L
        design["c"] = c
        APP_STATE.wes_design = design
        APP_STATE.spillwayProfile = True
        self.lbl_status.setText(
            f"<b>Saved:</b> Q_d = {Q_d} m³/s, L = {L} m, slope = {slope}  \u2014  "
            f"H_e = {design['H_e']:.3f} m, H_d = {design['H_d']:.3f} m, "
            f"V_1 = {design['V_1']:.2f} m/s.  "
            f"Spillway profile committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(800, self.close)
