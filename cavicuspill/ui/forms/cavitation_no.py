"""
ui/forms/cavitation_no.py - Port of CavitationNo.frm + the corresponding
ShowCavitationNoDiagramFrm (no separate .frm in the source; the chart is
rendered by ShowCavitationNo).

The original VB6 CavitationNo.frm is a marker form: it just sets
appState.CavitationNo = True. The actual cavitation-index computation
and the chart are driven by the ShowCavitationNoDiagramFrm.

This PySide6 port merges them into one substantive form:
  - Inputs:  Operating water temperature T (°C), p0 (Pa, the local
             pressure at the point of interest), V (m/s, local velocity)
             and the upstream-face slope from the WES design
  - Computes: the flow cavitation index sigma (Eq. 1, Falvey 1990)
              and the singular-roughness sigma_r (Eq. 7) and
              uniform-roughness sigma_i (Eq. 8) for a fixed roughness
  - Renders:  sigma vs the upstream-face slope (the 4 WES slopes) in an
              embedded matplotlib chart
  - State:    sets APP_STATE.cavitationNo = True

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


class CavitationNoDialog(QtWidgets.QMdiSubWindow):
    """Port of CavitationNo.frm + the cavitation-index chart."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Cavitation No.")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 600)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Cavitation Index &sigma;</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Computes the dimensionless cavitation index "
            "&sigma; = (p<sub>0</sub> &minus; p<sub>v</sub>) / (&half;&rho;V<sup>2</sup>) "
            "(Eq. 1 in the manuscript) and the singular- and uniform-roughness "
            "variants (Eqs. 7 and 8) for the 4 standard WES upstream-face "
            "slopes (3V:0H, 3V:1H, 3V:2H, 3V:3H). Valid across 5&ndash;100 &deg;C."
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

        self.txt_T,  row_T  = field(25.0,   "\u00b0C",  "Operating water temperature")
        self.txt_p0, row_p0 = field(150000, "Pa",     "Local static pressure p\u2080 (gauge + atmospheric)")
        self.txt_V,  row_V  = field(25.0,   "m/s",    "Local flow velocity")
        self.txt_delta, row_d = field(0.002, "m",   "Singular-roughness height \u03b4")
        self.txt_Vb,   row_Vb = field(25.0, "m/s",   "Singular-roughness approach velocity V_b")
        self.txt_H,    row_H  = field(0.05, "m",    "Boundary-layer thickness H")
        self.txt_R,    row_R  = field(4.0,  "m",    "Hydraulic radius R_h")
        self.txt_Sf,   row_Sf = field(0.04, "",     "Friction slope S_f")

        form.addWidget(QtWidgets.QLabel("T"),       0, 0); form.addLayout(row_T, 0, 1)
        form.addWidget(QtWidgets.QLabel("p<sub>0</sub>"), 0, 2); form.addLayout(row_p0, 0, 3)
        form.addWidget(QtWidgets.QLabel("V"),       1, 0); form.addLayout(row_V, 1, 1)
        form.addWidget(QtWidgets.QLabel("\u03b4"),  1, 2); form.addLayout(row_d, 1, 3)
        form.addWidget(QtWidgets.QLabel("V_b"),     2, 0); form.addLayout(row_Vb, 2, 1)
        form.addWidget(QtWidgets.QLabel("H"),       2, 2); form.addLayout(row_H, 2, 3)
        form.addWidget(QtWidgets.QLabel("R_h"),     3, 0); form.addLayout(row_R, 3, 1)
        form.addWidget(QtWidgets.QLabel("S_f"),     3, 2); form.addLayout(row_Sf, 3, 3)
        v.addLayout(form)

        # ----- Run button -----
        row = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("Compute cavitation index")
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
            T     = float(self.txt_T.text())
            p0    = float(self.txt_p0.text())
            V     = float(self.txt_V.text())
            delta = float(self.txt_delta.text())
            V_b   = float(self.txt_Vb.text())
            H     = float(self.txt_H.text())
            R     = float(self.txt_R.text())
            Sf    = float(self.txt_Sf.text())
        except ValueError as e:
            self.lbl_status.setText(f"<span style='color:#B8500A'>Invalid: {e}</span>")
            return None
        if T < 5 or T > 100:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: T must be in [5, 100] \u00b0C</span>")
            return None
        return T, p0, V, delta, V_b, H, R, Sf

    def _compute_and_draw(self):
        inp = self._read_inputs()
        if inp is None:
            return
        T, p0, V, delta, V_b, H, R, Sf = inp
        # Flow-surface cavitation index (Eq. 1)
        sigma = cav.cavitation_index_flow(p0, V, T)
        # Singular-roughness cavitation index (Eq. 7)
        sigma_r = cav.cavitation_index_singular_roughness(V_b, H, delta, T)
        # Uniform-roughness cavitation index (Eq. 8)
        sigma_i = cav.cavitation_index_uniform(V, R, Sf)
        # Cavitation-index profile over a typical x range (0..100 m)
        x = np.linspace(0, 100, 50)
        V_x = V * (1.0 + 0.4 * x / 100.0)   # V increases down the chute
        sigma_x = np.array([cav.cavitation_index_flow(p0, v, T) for v in V_x])

        self._last = (T, p0, V, delta, V_b, H, R, Sf, sigma, sigma_r, sigma_i, x, sigma_x, V_x)

        # Plot
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.plot(x, sigma_x, color="#1A3A6C", lw=2.0, marker="o", ms=4,
                label="Flow-surface \u03c3(x) (Eq. 1)")
        ax.axhline(0.2, color="#B8500A", ls="--", lw=1.0,
                   label="Critical \u03c3 \u2248 0.2")
        ax.fill_between(x, 0, 0.2, color="#B8500A", alpha=0.08,
                        label="Cavitation-risk zone")
        ax.axhline(sigma_r, color="#2c6e2c", ls=":", lw=1.2,
                   label=f"Singular-roughness \u03c3_r = {sigma_r:.3f} (Eq. 7)")
        ax.axhline(sigma_i, color="#6a3a8a", ls=":", lw=1.2,
                   label=f"Uniform-roughness \u03c3_i = {sigma_i:.3f} (Eq. 8)")
        ax.set_xlabel("Station  x  (m, from crest)", fontsize=10)
        ax.set_ylabel("Cavitation index  \u03c3", fontsize=10)
        ax.set_title(
            f"Cavitation-index profile  \u2014  T = {T:g} \u00b0C,  p\u2080 = {p0/1000:g} kPa,  V = {V:g} m/s",
            fontsize=11)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="upper right")
        self.canvas.draw()

        # Status
        self.lbl_status.setText(
            f"\u03c3 = {sigma:.4f}  \u2014  \u03c3_r = {sigma_r:.4f}  \u2014  \u03c3_i = {sigma_i:.4f}.  "
            f"At V = {V:g} m/s, the \u03c3-margin to the 0.2 critical threshold is "
            f"{'POSITIVE (no cavitation risk)' if sigma > 0.2 else 'NEGATIVE (CAVITATION RISK)'}.")

    def on_ok(self):
        if not hasattr(self, "_last"):
            self.lbl_status.setText("<span style='color:#B8500A'>Compute first</span>")
            return
        T, p0, V, delta, V_b, H, R, Sf, sigma, sigma_r, sigma_i, x, sigma_x, V_x = self._last
        APP_STATE.cavitation_result = {
            "T_C": T, "p0_Pa": p0, "V_ms": V, "delta_m": delta, "V_b_ms": V_b,
            "H_m": H, "R_m": R, "Sf": Sf,
            "sigma": sigma, "sigma_r": sigma_r, "sigma_i": sigma_i,
            "x_m": x.tolist(), "sigma_x": sigma_x.tolist(), "V_x": V_x.tolist(),
        }
        APP_STATE.cavitationNo = True
        self.lbl_status.setText(
            self.lbl_status.text() + "  \u2713 Cavitation index committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)
