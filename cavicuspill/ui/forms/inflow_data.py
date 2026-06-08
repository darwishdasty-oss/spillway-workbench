"""
ui/forms/inflow_data.py - Port of InFlowData.frm

The original VB6 form has:
  - An editable FlexGrid (VSFlex7) of (time h, Q m^3/s) pairs
  - A "Create Table" button that sizes the grid
  - OK / Cancel buttons
  - On OK, reads the (t, Q) data into InFlowDataS.gridInput

This PySide6 port:
  - Replaces the VSFlex7 grid with a QTableWidget (2 columns)
  - On OK, builds cavicuspill.InflowHydrograph and stores in APP_STATE
  - Updates APP_STATE.inFlow = True

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


class InflowDataDialog(QtWidgets.QMdiSubWindow):
    """Port of InFlowData.frm."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Inflow Data")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(540, 480)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Inflow Data</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Enter the inflow unit hydrograph as a list of (time in hours, "
            "discharge in m³/s) pairs. Time must be strictly increasing. "
            "Then click <b>OK</b> to commit it to the project state."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Number-of-rows control -----
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Number of intervals (n):"))
        self.txt_n = QtWidgets.QLineEdit("12")
        self.txt_n.setMaximumWidth(80)
        self.txt_n.setToolTip("The number of (t, Q) pairs in the hydrograph")
        row1.addWidget(self.txt_n)
        self.btn_create = QtWidgets.QPushButton("Create Table")
        self.btn_create.clicked.connect(self.on_create_table)
        row1.addWidget(self.btn_create)
        row1.addStretch(1)
        v.addLayout(row1)

        # ----- Data grid (2 columns: time h, Q m^3/s) -----
        self.table = QtWidgets.QTableWidget(13, 2)
        self.table.setHorizontalHeaderLabels(["time (h)", "Q (m³/s)"])
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        for i in range(2):
            hh = self.table.horizontalHeaderItem(i)
            f = hh.font(); f.setBold(True); hh.setFont(f)
        # Pre-fill a 12-row example hydrograph (mirrors the manuscript's
        # default 2005 example: triangular, peak at hour 8)
        defaults_t = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
        defaults_Q = [50, 200, 500, 1100, 2200, 2700, 1900, 1100, 600, 350, 200, 100]
        for r in range(12):
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(defaults_t[r])))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(defaults_Q[r])))
        for r in range(12, 13):
            for c in range(2):
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(""))
        v.addWidget(self.table, 1)

        # ----- Status line -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

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
        if APP_STATE.inflow is not None:
            inf = APP_STATE.inflow
            self.txt_n.setText(str(inf.n))
            self.on_create_table()
            for r in range(inf.n):
                self.table.item(r, 0).setText(f"{inf.t_h[r]:g}")
                self.table.item(r, 1).setText(f"{inf.Q[r]:g}")

    def on_create_table(self):
        n_txt = self.txt_n.text().strip()
        if not n_txt.lstrip("-").isdigit():
            QtWidgets.QMessageBox.warning(self, "Invalid n",
                "Please enter a positive integer in the n field.")
            self.txt_n.setFocus()
            return
        n = int(n_txt)
        if n < 1:
            QtWidgets.QMessageBox.warning(self, "Invalid n",
                "n must be at least 1.")
            return
        self.table.setRowCount(n)
        for r in range(n):
            for c in range(2):
                it = self.table.item(r, c)
                if it is None:
                    self.table.setItem(r, c, QtWidgets.QTableWidgetItem(""))
        self.lbl_status.setText(f"Grid resized to {n} rows.")

    def on_ok(self):
        # 1. SpillwayData must be entered first (the routing needs G-Q)
        if APP_STATE.spillway_cfg is None:
            QtWidgets.QMessageBox.critical(self, "Spillway not entered",
                "Please enter the Spillway Data first "
                "(Flood Routing > 2. Spillway Data).")
            return
        # 2. Validate n
        try:
            n = int(self.txt_n.text())
        except ValueError:
            QtWidgets.QMessageBox.critical(self, "Invalid n",
                "n must be a positive integer.")
            return
        if n < 1:
            QtWidgets.QMessageBox.critical(self, "Invalid n",
                "n must be at least 1.")
            return
        # 3. Validate all cells are numeric
        t = np.zeros(n)
        Q = np.zeros(n)
        for r in range(n):
            for c, arr in [(0, t), (1, Q)]:
                txt = self.table.item(r, c).text().strip()
                try:
                    arr[r] = float(txt)
                except ValueError:
                    QtWidgets.QMessageBox.critical(self, "Invalid cell",
                        f"Row {r+1}, column {c+1} is not numeric: '{txt}'.")
                    return
        # 4. Validate times strictly increasing
        for r in range(1, n):
            if t[r] <= t[r - 1]:
                QtWidgets.QMessageBox.critical(self, "Invalid times",
                    f"Row {r+1}: time {t[r]} must be greater than previous {t[r-1]}.")
                return
        # 5. Build InflowHydrograph
        APP_STATE.inflow = cav.InflowHydrograph(n=n, t_h=t, Q=Q)
        APP_STATE.inFlow = True
        # 6. Status
        peak = float(Q.max())
        t_peak = float(t[int(Q.argmax())])
        self.lbl_status.setText(
            f"Saved: {n} intervals, peak Q = {peak:.1f} m³/s at t = {t_peak:g} h.  "
            f"Outflow (Pulse-Method) menu is now enabled.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(700, self.close)
