"""
ui/forms/surface_profile.py - Port of SurfaceProfile.frm + ProfileData.frm

The original VB6 has two related forms:
  - ProfileData.frm  (the input: Q, n, slope, distance from crest to toe,
                       cross-section dimensions)
  - SurfaceProfile.frm (a marker form: just sets appState.SurfaceProfile)

This PySide6 port merges them into one form:
  - Inputs:  Q (m^3/s), Manning n, bed slope S0, initial depth y0,
             reach (m), step dx (m), width b (m)
  - On OK, runs cav.standard_step() (1:1 with the Standard Step Method,
    Eq. 5 in the manuscript) and renders the water-surface profile in
    an embedded matplotlib chart
  - On OK, sets APP_STATE.surfaceProfile = True

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


class SurfaceProfileDialog(QtWidgets.QMdiSubWindow):
    """Port of SurfaceProfile.frm + ProfileData.frm (Standard Step)."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Surface Profile (Standard Step Method)")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 600)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Surface Profile &mdash; "
            "Standard Step Method</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Computes the backwater profile along a rectangular chute by "
            "direct-step iteration on the energy equation "
            "dy/dx = (S<sub>0</sub> &minus; S<sub>f</sub>) / (1 &minus; Fr<sup>2</sup>). "
            "1:1 port of the Standard Step Method (Eq. 5 in the manuscript)."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Input grid -----
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        def field(default, unit, tooltip=""):
            edit = QtWidgets.QLineEdit(str(default))
            edit.setMaximumWidth(110)
            if tooltip:
                edit.setToolTip(tooltip)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(edit)
            row.addWidget(QtWidgets.QLabel(f"<span style='color:#888'>{unit}</span>"))
            row.addStretch(1)
            return edit, row

        self.txt_Q,   row_Q   = field(2700.0, "m³/s", "Discharge")
        self.txt_b,   row_b   = field(30.0,   "m",    "Channel width (rectangular)")
        self.txt_n,   row_n   = field(0.014,  "",     "Manning's n")
        self.txt_S0,  row_S0  = field(0.04,   "",     "Bed slope (m/m, positive downward)")
        self.txt_y0,  row_y0  = field(4.5,    "m",    "Initial depth at x=0")
        self.txt_dx,  row_dx  = field(5.0,    "m",    "Step length")
        self.txt_L,   row_L   = field(200.0,  "m",    "Reach (total length)")

        form.addWidget(QtWidgets.QLabel("Q"),       0, 0); form.addLayout(row_Q,  0, 1)
        form.addWidget(QtWidgets.QLabel("b"),       0, 2); form.addLayout(row_b,  0, 3)
        form.addWidget(QtWidgets.QLabel("n"),       1, 0); form.addLayout(row_n,  1, 1)
        form.addWidget(QtWidgets.QLabel("S<sub>0</sub>"), 1, 2); form.addLayout(row_S0, 1, 3)
        form.addWidget(QtWidgets.QLabel("y<sub>0</sub>"), 2, 0); form.addLayout(row_y0, 2, 1)
        form.addWidget(QtWidgets.QLabel("dx"),      2, 2); form.addLayout(row_dx, 2, 3)
        form.addWidget(QtWidgets.QLabel("L"),       3, 0); form.addLayout(row_L,  3, 1)
        v.addLayout(form)

        # ----- Run button -----
        row = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("Compute Profile")
        self.btn_run.clicked.connect(self._compute_and_draw)
        row.addWidget(self.btn_run)
        row.addStretch(1)
        v.addLayout(row)

        # ----- Chart -----
        self.canvas = MplCanvas(7.0, 3.5, dpi=100)
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

        # Initial computation
        self._compute_and_draw()

    def _read_inputs(self):
        try:
            Q  = float(self.txt_Q.text())
            b  = float(self.txt_b.text())
            n  = float(self.txt_n.text())
            S0 = float(self.txt_S0.text())
            y0 = float(self.txt_y0.text())
            dx = float(self.txt_dx.text())
            L  = float(self.txt_L.text())
        except ValueError as e:
            self.lbl_status.setText(
                f"<span style='color:#B8500A'>Invalid: {e}</span>")
            return None
        if Q <= 0 or b <= 0 or n <= 0 or S0 <= 0 or y0 <= 0 or dx <= 0 or L <= 0:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: all values must be positive</span>")
            return None
        n_steps = int(L / dx)
        return Q, b, n, S0, y0, dx, n_steps

    def _compute_and_draw(self):
        inp = self._read_inputs()
        if inp is None:
            return
        Q, b, n, S0, y0, dx, n_steps = inp
        x, y, V = cav.standard_step(Q, b, n, S0, y0, dx, n_steps)
        self._last = (x, y, V, Q, b, n, S0, y0, dx, n_steps)

        # Plot
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.plot(x, y, color="#1A3A6C", lw=2.0, label="Water surface y(x)")
        bed = np.array([(x[-1] - xi) * S0 for xi in x])
        ax.plot(x, bed, color="#888", lw=1.0, ls="--", label=f"Bed (S\u2080 = {S0})")
        # Annotate
        i_term = -1
        ax.annotate(f"y({x[i_term]:.0f} m) = {y[i_term]:.2f} m\n"
                    f"V({x[i_term]:.0f} m) = {V[i_term]:.2f} m/s",
                    xy=(x[i_term], y[i_term]),
                    xytext=(-100, 30), textcoords="offset points",
                    fontsize=9, color="#B8500A",
                    arrowprops=dict(arrowstyle="->", color="#B8500A"))
        ax.set_xlabel("Distance  x  (m)", fontsize=10)
        ax.set_ylabel("Elevation  y  (m)", fontsize=10)
        ax.set_title(
            f"Standard Step water-surface profile  \u2014  "
            f"Q = {Q} m\u00b3/s,  b = {b} m,  n = {n},  S\u2080 = {S0}",
            fontsize=11)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="lower left")
        self.canvas.draw()

        Fr = V / np.sqrt(9.81 * y)
        self.lbl_status.setText(
            f"Computed {n_steps} steps over {x[-1]:.0f} m.  "
            f"Terminal: y = {y[-1]:.3f} m,  V = {V[-1]:.3f} m/s,  Fr = {Fr[-1]:.3f}.  "
            f"Click <b>OK</b> to commit to APP_STATE.")

    def on_ok(self):
        if not hasattr(self, "_last"):
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Compute the profile first</span>")
            return
        x, y, V, Q, b, n, S0, y0, dx, n_steps = self._last
        APP_STATE.surface_profile = {
            "Q": Q, "b": b, "n": n, "S0": S0, "y0": y0, "dx": dx, "n_steps": n_steps,
            "x": x.tolist(), "y": y.tolist(), "V": V.tolist(),
        }
        APP_STATE.surfaceProfile = True
        self.lbl_status.setText(
            self.lbl_status.text() + "  \u2713 Profile committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)
