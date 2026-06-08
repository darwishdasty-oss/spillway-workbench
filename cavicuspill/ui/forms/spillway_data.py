"""
ui/forms/spillway_data.py - Port of SpillWayData.frm

The original VB6 form has:
  - 5 TextBox inputs: L_min (m), L_max (m), b (m, increment), c (discharge
    coefficient), DeltaT (h, routing time step)
  - OK / Cancel buttons
  - On OK, validates each field is numeric, that L_max > L_min, that
    b < (L_max - L_min), and calls calc() which precomputes the G-Q
    curves for all candidate spillway lengths.

This PySide6 port:
  - Replaces the TextBoxes with QLineEdit
  - On OK, calls cavicuspill.precompute_gq_curves() (1:1 with VB6 calc)
  - Stores the G-Q curves in APP_STATE for downstream forms to consume
  - Updates APP_STATE.spillwayData = True and enables the Inflow menu

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


class SpillwayDataDialog(QtWidgets.QMdiSubWindow):
    """Port of SpillWayData.frm."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Spillway Data")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(540, 360)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Spillway Data</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Define the candidate spillway lengths (L<sub>min</sub>, L<sub>max</sub>, "
            "and the increment b), the discharge coefficient C, and the routing "
            "time step &Delta;t. The Pulse-Method routing will be performed for "
            "all (L<sub>max</sub> &minus; L<sub>min</sub>) / b + 1 lengths."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Input fields -----
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignLeft)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        def field(default, unit, tooltip=""):
            row = QtWidgets.QHBoxLayout()
            edit = QtWidgets.QLineEdit(str(default))
            edit.setMinimumWidth(140)
            row.addWidget(edit)
            row.addWidget(QtWidgets.QLabel(f"<span style='color:#888'>{unit}</span>"))
            row.addStretch(1)
            if tooltip:
                edit.setToolTip(tooltip)
            return edit, row

        self.txt_Lmin, row_lmin = field(70.0, "m",  "Minimum candidate spillway length")
        self.txt_Lmax, row_lmax = field(80.0, "m",  "Maximum candidate spillway length")
        self.txt_b,   row_b   = field(5.0,  "m",  "Increment between candidate lengths")
        self.txt_c,   row_c   = field(2.225, "",  "Discharge coefficient (USBR default 2.225)")
        self.txt_dt,  row_dt  = field(2.0,  "h",  "Routing time step (hours)")

        form.addRow("L<sub>min</sub>", row_lmin)
        form.addRow("L<sub>max</sub>", row_lmax)
        form.addRow("b",               row_b)
        form.addRow("C",               row_c)
        form.addRow("&Delta;t",        row_dt)
        v.addLayout(form)

        # ----- Live preview of the candidate lengths -----
        self.lbl_preview = QtWidgets.QLabel("")
        self.lbl_preview.setStyleSheet("color:#1A3A6C; font-size:9pt; font-style:italic;")
        v.addWidget(self.lbl_preview)
        for f in [self.txt_Lmin, self.txt_Lmax, self.txt_b]:
            f.textChanged.connect(self._update_preview)
        self._update_preview()

        # ----- Status line -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

        v.addStretch(1)

        # ----- Cancel / OK -----
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
        if APP_STATE.spillway_cfg is not None:
            sw = APP_STATE.spillway_cfg
            self.txt_Lmin.setText(f"{sw.L_min:g}")
            self.txt_Lmax.setText(f"{sw.L_max:g}")
            self.txt_b.setText(f"{sw.b:g}")
            self.txt_c.setText(f"{sw.c:g}")
            self.txt_dt.setText(f"{sw.deltaT:g}")

    def _update_preview(self):
        try:
            Lmin = float(self.txt_Lmin.text())
            Lmax = float(self.txt_Lmax.text())
            b    = float(self.txt_b.text())
            n    = int((Lmax - Lmin) / b) + 1 if b > 0 and Lmax > Lmin else 0
            self.lbl_preview.setText(
                f"Candidate lengths: "
                f"L = {Lmin:g}, {Lmin + b:g}, ..., {Lmin + (n-1)*b:g} m  "
                f"({n} values)" if n > 0 else
                f"<span style='color:#B8500A'>Invalid: Lmax &le; Lmin or b &le; 0</span>")
        except ValueError:
            self.lbl_preview.setText("")

    def on_ok(self):
        # 1. Validate all fields numeric
        try:
            Lmin = float(self.txt_Lmin.text())
            Lmax = float(self.txt_Lmax.text())
            b    = float(self.txt_b.text())
            c    = float(self.txt_c.text())
            dt   = float(self.txt_dt.text())
        except ValueError:
            QtWidgets.QMessageBox.critical(self, "Invalid input",
                "L_min, L_max, b, C, and Delta_t must all be numeric.")
            return
        # 2. Cross-field validation (verbatim from VB6 fillDatas)
        if Lmax <= Lmin:
            QtWidgets.QMessageBox.critical(self, "Invalid L",
                "L_max must be greater than L_min.")
            return
        if (Lmax - Lmin) < b:
            QtWidgets.QMessageBox.critical(self, "Invalid b",
                "b is invalid (must be less than L_max - L_min).")
            return
        if c <= 0 or dt <= 0 or b <= 0:
            QtWidgets.QMessageBox.critical(self, "Invalid values",
                "C, b, and Delta_t must all be positive.")
            return
        # 3. Reservoir must be entered first
        if APP_STATE.reservoir_data is None:
            QtWidgets.QMessageBox.critical(self, "Reservoir not entered",
                "Please enter the Reservoir Properties first "
                "(Flood Routing > 1. Reservoir Properties).")
            return
        # 4. Build the spillway config and precompute G-Q curves
        sw = cav.SpillwayConfig(L_min=Lmin, L_max=Lmax, b=b, c=c, deltaT=dt)
        L_data_list = cav.precompute_gq_curves(APP_STATE.reservoir_data, sw)
        # 5. Update APP_STATE
        APP_STATE.spillway_cfg = sw
        APP_STATE.spillwayData = True
        # 6. Status
        lengths = ", ".join(f"{L:g}" for L, _, _ in L_data_list)
        self.lbl_status.setText(
            f"Saved: L &isin; [{Lmin:g}, {Lmax:g}], b = {b:g}, C = {c:g}, "
            f"&Delta;t = {dt:g} h.  {len(L_data_list)} G-Q curves precomputed "
            f"for L = {lengths} m.  Inflow Data menu is now enabled.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(600, self.close)
