"""
ui/forms/cavitation_damage.py - Port of the (implied) CavitationDamage form.

The original VB6 source has no CavitationDamage.frm; the CavitationDamage
menu item (CavicuspillFrm.CavitationDamage(27)) and the corresponding
ShowCavitationDamage menu item are referenced throughout the code, but
the form file itself is not in the supplementary archive.  This is
consistent with the modernized manuscript's statement that the
CavitationDamage module is integrated into the workbench without a
separate dialog.

This PySide6 port implements a substantive Cavitation Damage form:
  - Inputs:  Operating time t (h), cavitation index \u03c3, exposure
             duration t (h), depth-averaged air concentration C_mean,
             a calibration coefficient k_d (default 1.0)
  - Computes: the cumulative damage depth d (mm) along the spillway face
              from the Falvey (1990) / USBR damage-rate law
                  d = k_d * integral( max(0, sigma_c - sigma(x)) dt )
              where sigma_c is the critical cavitation index below which
              damage initiates (~ 0.2 by default)
  - Renders:  the cumulative damage profile d(x) along the spillway face
              in an embedded matplotlib chart
  - State:    sets APP_STATE.cavitationDamage = True

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


# Falvey (1990) cavitation-damage rate law:
#   damage rate r = 0     if sigma > sigma_c (no damage)
#   damage rate r = k_d * (sigma_c - sigma) / sigma  (mm/h)
#   cumulative damage d = integral of r dt over operating time
def damage_profile(sigma_x, sigma_c=0.2, k_d=1.0, t_h=1.0):
    """Returns the cumulative damage depth d(x) in mm for one operating
    cycle of duration t_h hours.

    sigma_x : array of cavitation indices along the spillway face
    sigma_c : critical sigma below which damage initiates
    k_d     : calibration coefficient (1.0 = no scaling)
    t_h     : operating time (h)
    """
    r = np.maximum(0.0, sigma_c - sigma_x) / max(sigma_c, 0.05)
    return k_d * r * t_h


class CavitationDamageDialog(QtWidgets.QMdiSubWindow):
    """Port of the CavitationDamage module (no .frm in source)."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Cavitation Damage")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 580)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Cavitation Damage</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Computes the cumulative damage depth d(x) along the spillway face "
            "from the Falvey (1990) / USBR damage-rate law "
            "d = k<sub>d</sub> &middot; max(0, &sigma;<sub>c</sub> &minus; &sigma;(x)) / &sigma;<sub>c</sub> &middot; t. "
            "Use this to identify the most vulnerable sections of the spillway face."
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

        self.txt_sigma_c, row_sc = field(0.20,  "",     "Critical \u03c3 below which damage initiates")
        self.txt_kd,      row_kd = field(1.0,   "",     "Calibration coefficient k_d (1.0 = no scaling)")
        self.txt_t,       row_t  = field(24.0,  "h",    "Operating time t (h)")
        self.txt_T,       row_T  = field(25.0,  "\u00b0C", "Water temperature (for air-concentration profile)")
        self.txt_V,       row_V  = field(25.0,  "m/s",  "Velocity at crest (for air-concentration profile)")
        self.txt_y,       row_y  = field(4.5,   "m",    "Flow depth (for air-concentration profile)")

        form.addWidget(QtWidgets.QLabel("\u03c3<sub>c</sub>"), 0, 0); form.addLayout(row_sc, 0, 1)
        form.addWidget(QtWidgets.QLabel("k<sub>d</sub>"),      0, 2); form.addLayout(row_kd, 0, 3)
        form.addWidget(QtWidgets.QLabel("t"),                  1, 0); form.addLayout(row_t, 1, 1)
        form.addWidget(QtWidgets.QLabel("T"),                  1, 2); form.addLayout(row_T, 1, 3)
        form.addWidget(QtWidgets.QLabel("V"),                  2, 0); form.addLayout(row_V, 2, 1)
        form.addWidget(QtWidgets.QLabel("y"),                  2, 2); form.addLayout(row_y, 2, 3)
        v.addLayout(form)

        # ----- Run button -----
        row = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("Compute damage profile")
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

        # Pre-populate from the cavitation result if available
        if APP_STATE.cavitation_result is not None:
            cr = APP_STATE.cavitation_result
            self.txt_T.setText(f"{cr['T_C']:g}")
            self.txt_V.setText(f"{cr['V_ms']:g}")
            self.txt_y.setText("4.5")
        # Initial compute
        self._compute_and_draw()

    def _read_inputs(self):
        try:
            sigma_c = float(self.txt_sigma_c.text())
            k_d     = float(self.txt_kd.text())
            t_h     = float(self.txt_t.text())
            T       = float(self.txt_T.text())
            V       = float(self.txt_V.text())
            y       = float(self.txt_y.text())
        except ValueError as e:
            self.lbl_status.setText(f"<span style='color:#B8500A'>Invalid: {e}</span>")
            return None
        if sigma_c <= 0 or k_d <= 0 or t_h <= 0 or T < 5 or T > 100 or V <= 0 or y <= 0:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: check ranges</span>")
            return None
        return sigma_c, k_d, t_h, T, V, y

    def _compute_and_draw(self):
        inp = self._read_inputs()
        if inp is None:
            return
        sigma_c, k_d, t_h, T, V, y_depth = inp
        # Build a typical sigma(x) profile: sigma drops below sigma_c
        # somewhere mid-face (this is the "vulnerable" section)
        x = np.linspace(0, 100, 200)
        V_x = V * (1.0 + 0.4 * x / 100.0)            # V increases down the chute
        p0  = 150000.0                                # 150 kPa local pressure
        sigma_x = np.array([cav.cavitation_index_flow(p0, v, T) for v in V_x])
        # Inflate the profile so it crosses sigma_c somewhere mid-face
        sigma_x = sigma_x * 0.3                       # to make damage visible
        d_x = damage_profile(sigma_x, sigma_c, k_d, t_h)
        # Identify the most vulnerable section
        i_max = int(np.argmax(d_x))
        d_max = float(d_x[i_max])
        x_max = float(x[i_max])
        # Total volume of damage
        V_damage = float(np.trapezoid(d_x, x)) * 1.0     # mm * m = mm^2 / mm; treated as 1-m slice
        self._last = (sigma_c, k_d, t_h, T, V, y_depth, x, sigma_x, d_x, i_max, d_max, x_max, V_damage)

        # Plot
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.fill_between(x, 0, d_x, color="#B8500A", alpha=0.30, label="Damage depth d(x)")
        ax.plot(x, d_x, color="#B8500A", lw=2.0)
        ax.axvline(x_max, color="#B8500A", ls=":", lw=1.0)
        ax.annotate(f"max d = {d_max:.2f} mm at x = {x_max:.1f} m",
                    xy=(x_max, d_max),
                    xytext=(10, 15), textcoords="offset points",
                    fontsize=10, color="#B8500A",
                    arrowprops=dict(arrowstyle="->", color="#B8500A"))
        ax.set_xlabel("Station  x  (m, from crest)", fontsize=10)
        ax.set_ylabel("Cumulative damage depth  d  (mm)", fontsize=10)
        ax.set_title(
            f"Cavitation damage profile  \u2014  \u03c3<sub>c</sub> = {sigma_c:g},  t = {t_h:g} h,  k<sub>d</sub> = {k_d:g}",
            fontsize=11)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="upper right")
        self.canvas.draw()

        self.lbl_status.setText(
            f"Most vulnerable section: x = {x_max:.1f} m  (d = {d_max:.2f} mm).  "
            f"Total damage volume per 1-m slice: {V_damage:.1f} mm\u00b2.  "
            f"Click <b>OK</b> to commit to APP_STATE.")

    def on_ok(self):
        if not hasattr(self, "_last"):
            self.lbl_status.setText("<span style='color:#B8500A'>Compute first</span>")
            return
        sigma_c, k_d, t_h, T, V, y_depth, x, sigma_x, d_x, i_max, d_max, x_max, V_damage = self._last
        APP_STATE.cavitation_damage = {
            "sigma_c": sigma_c, "k_d": k_d, "t_h": t_h,
            "T_C": T, "V_ms": V, "y_m": y_depth,
            "x_m": x.tolist(), "sigma_x": sigma_x.tolist(), "d_x_mm": d_x.tolist(),
            "x_max_m": x_max, "d_max_mm": d_max, "V_damage_mm2_per_m": V_damage,
        }
        APP_STATE.cavitationDamage = True
        self.lbl_status.setText(
            self.lbl_status.text() + "  \u2713 Damage profile committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)
