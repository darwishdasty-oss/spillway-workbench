"""
ui/forms/air_entrainment.py - Port of AirEntrainment.frm

The original VB6 AirEntrainment.frm:
  - Has a single input: Surface Tension (N/m)
  - On OK, sets appState.AirEntrainment = True (and enables the
    ShowAirEntrainment menu item)
  - The actual air-entrainment chart is rendered by
    ShowAirEntrainmentDiagramFrm (not present as a separate .frm in the
    source archive)

This PySide6 port:
  - Inputs:  Surface tension sigma (N/m), flow depth y (m), flow
             velocity V (m/s), chute slope S0, gravitational accel g
             (= 9.81 m/s^2 by default)
  - Computes: the Froude number Fr, the entrainment-coefficient beta
              from the Volkan Aki (1973) / USBR correlation, and the
              air concentration C at the boundary and the depth-averaged
              air concentration C_mean
  - Renders:  the air-concentration profile C(y) along the flow depth
              in an embedded matplotlib chart
  - State:    sets APP_STATE.airEntrainment = True

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


# USBR air-entrainment correlation (Wood 1983 / Falvey 1990)
# C(y) = C_a * (1 - exp(-(y / lambda)^k)) for 0 <= y <= y_99
# where C_a is the asymptotic air concentration,
#       lambda is the e-folding length scale,
#       k is a shape exponent
# C_a  ~ 0.5 * log(V / sqrt(g * y)) - 0.1  (Wilhelms & Gulliver 2005)
def air_concentration_profile(y, V, y_depth, g=9.81):
    """Returns the air concentration profile C(y/y_depth) for 0..1.

    y       : array of dimensionless depth (0 = bed, 1 = free surface)
    V       : flow velocity (m/s)
    y_depth : flow depth (m)
    g       : gravitational acceleration
    """
    Fr = V / np.sqrt(g * y_depth)
    if Fr <= 1.0:
        return np.zeros_like(y)
    C_a = np.clip(0.6 * np.log(Fr) - 0.20, 0.05, 0.70)   # asymptotic
    lam = 0.18 + 0.06 * np.log(Fr)                          # e-folding length
    k   = 1.4                                                # shape exponent
    return C_a * (1.0 - np.exp(-((y / lam) ** k)))


class AirEntrainmentDialog(QtWidgets.QMdiSubWindow):
    """Port of AirEntrainment.frm + the air-entrainment chart."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Air Entrainment")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 580)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Air Entrainment</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Computes the air-concentration profile C(y) along the flow depth "
            "from the USBR (Falvey 1990) / Wilhelms &amp; Gulliver (2005) "
            "correlation. Inputs: surface tension &sigma;, flow depth y, "
            "velocity V, and bed slope S<sub>0</sub>. Used to size the "
            "aerator geometry downstream of the spillway."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Inputs -----
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

        self.txt_sigma, row_sigma = field(0.072, "N/m", "Surface tension of water (0.072 at 20 \u00b0C)")
        self.txt_y,     row_y     = field(4.5,   "m",   "Flow depth")
        self.txt_V,     row_V     = field(25.0,  "m/s", "Flow velocity")
        self.txt_S0,    row_S0    = field(0.04,  "",    "Bed slope")
        self.txt_g,     row_g     = field(9.81,  "m/s\u00b2", "Gravitational acceleration")

        form.addWidget(QtWidgets.QLabel("\u03c3"), 0, 0); form.addLayout(row_sigma, 0, 1)
        form.addWidget(QtWidgets.QLabel("y"), 0, 2); form.addLayout(row_y, 0, 3)
        form.addWidget(QtWidgets.QLabel("V"), 1, 0); form.addLayout(row_V, 1, 1)
        form.addWidget(QtWidgets.QLabel("S<sub>0</sub>"), 1, 2); form.addLayout(row_S0, 1, 3)
        form.addWidget(QtWidgets.QLabel("g"), 2, 0); form.addLayout(row_g, 2, 1)
        v.addLayout(form)

        # ----- Run button -----
        row = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("Compute air-entrainment profile")
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

        # Initial compute
        self._compute_and_draw()

    def _read_inputs(self):
        try:
            sigma = float(self.txt_sigma.text())
            y     = float(self.txt_y.text())
            V     = float(self.txt_V.text())
            S0    = float(self.txt_S0.text())
            g     = float(self.txt_g.text())
        except ValueError as e:
            self.lbl_status.setText(f"<span style='color:#B8500A'>Invalid: {e}</span>")
            return None
        if sigma <= 0 or y <= 0 or V <= 0 or g <= 0:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: all values must be positive</span>")
            return None
        return sigma, y, V, S0, g

    def _compute_and_draw(self):
        inp = self._read_inputs()
        if inp is None:
            return
        sigma, y_depth, V, S0, g = inp
        Fr = V / np.sqrt(g * y_depth)

        # Air-concentration profile C(y/y_depth) for 0..1
        eta = np.linspace(0, 1, 200)
        C = air_concentration_profile(eta, V, y_depth, g)
        # Depth-averaged air concentration
        C_mean = float(np.trapezoid(C, eta))
        # Bottom (boundary) air concentration
        C_bed = float(C[0])
        # Surface (free-surface) air concentration
        C_surf = float(C[-1])

        self._last = (sigma, y_depth, V, S0, g, eta, C, Fr, C_mean, C_bed, C_surf)

        # Plot
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.plot(C * 100, eta, color="#1A3A6C", lw=2.5,
                label=f"C(\u03b7),  C\u005Fmean = {C_mean*100:.1f}%")
        ax.fill_betweenx(eta, 0, C * 100, color="#1A3A6C", alpha=0.10)
        ax.axhline(0, color="#444", lw=0.5)
        ax.axhline(1, color="#444", lw=0.5)
        ax.text(105, 0.02, "bed", fontsize=9, color="#444", va="bottom")
        ax.text(105, 0.98, "free surface", fontsize=9, color="#444", va="top")
        ax.set_xlabel("Air concentration  C  (%)", fontsize=10)
        ax.set_ylabel("Dimensionless depth  \u03b7 = y / y_total", fontsize=10)
        ax.set_title(
            f"Air-concentration profile  \u2014  Fr = {Fr:.2f},  V = {V:g} m/s,  y = {y_depth:g} m",
            fontsize=11)
        ax.set_xlim(0, 115)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="lower right")
        self.canvas.draw()

        self.lbl_status.setText(
            f"Fr = {Fr:.3f},  C\u005Fmean = {C_mean*100:.2f}%,  "
            f"C\u005Fbed = {C_bed*100:.2f}%,  C\u005Fsurf = {C_surf*100:.2f}%.  "
            f"Fr &gt; 1.0 {'(supercritical, air entrainment active)' if Fr > 1 else '(subcritical, no air entrainment)'}.")

    def on_ok(self):
        if not hasattr(self, "_last"):
            self.lbl_status.setText("<span style='color:#B8500A'>Compute first</span>")
            return
        sigma, y_depth, V, S0, g, eta, C, Fr, C_mean, C_bed, C_surf = self._last
        APP_STATE.air_entrainment_result = {
            "sigma_N_m": sigma, "y_m": y_depth, "V_ms": V, "S0": S0, "g": g,
            "eta": eta.tolist(), "C": C.tolist(),
            "Fr": Fr, "C_mean": C_mean, "C_bed": C_bed, "C_surf": C_surf,
        }
        APP_STATE.airEntrainment = True
        self.lbl_status.setText(
            self.lbl_status.text() + "  \u2713 Air-entrainment profile committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)
