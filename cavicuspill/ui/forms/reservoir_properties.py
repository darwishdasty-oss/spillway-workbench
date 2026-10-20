"""
ui/forms/reservoir_properties.py - Port of ReservoirProperties.frm

The original VB6 form has:
  - 4 TextBox inputs: E (spillway crest elevation, m),
    V (volume of E, m^3), n1 (number of heights), n2 (subdivisions)
  - A 3-column editable FlexGrid (VSFlex7): Row#, height (m), volume (m^3)
  - A "Create Table" command button that resizes the grid to n1+1 rows
  - OK / Cancel buttons
  - On OK, validates the grid, calls fillDatas() which:
      1. Reads E, V into globals
      2. Reads the grid rows (n1 rows of (h, V) starting at row 1)
      3. Interpolates a finer grid with n2 subdivisions between each pair
         of (h, V) values
      4. Stores the result in ReservoiPopertiesDatas.gridOutput
  - On OK, sets appState.reservoir = True, enables SpillwayData menu

This PySide6 port:
  - Replaces the VSFlex7 grid with a QTableWidget (3 columns)
  - Replaces the TextBoxes with QLineEdit
  - Replaces the OK / Cancel / Create Table buttons with QPushButton
  - On OK, calls cavicuspill.interpolate_reservoir_table() (1:1 with fillDatas)
  - Updates APP_STATE.reservoir / APP_STATE.reservoir_data on OK

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations
import os, sys
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

# Re-use the algorithm port
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cavicuspill as cav  # noqa: E402

# Pull APP_STATE from the MDI shell module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Use the same module-identity trick: import by full module path so that
# all forms share a single APP_STATE object across the test/demo.
import mdi_main as _mdi_main  # noqa: E402
APP_STATE = _mdi_main.APP_STATE


class ReservoirPropertiesDialog(QtWidgets.QMdiSubWindow):
    """Port of ReservoirProperties.frm."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Reservoir Properties")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 560)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            "<b style='color:#1A3A6C; font-size:13pt'>Reservoir Properties</b><br>"
            "<span style='color:#666; font-style:italic; font-size:9pt'>"
            "Enter the spillway crest elevation E, the volume at E, the number of "
            "heights n<sub>1</sub>, the subdivisions n<sub>2</sub>, then click "
            "<b>Create Table</b> to size the grid, fill the (h, V) values, and click "
            "<b>OK</b> to commit the elevation-storage table to the project state."
            "</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Top row: 4 inputs (E, V, n1, n2) -----
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        e_lbl = QtWidgets.QLabel("E &nbsp;<span style='color:#888'>(spillway crest elev., m)</span>")
        v_lbl = QtWidgets.QLabel("V &nbsp;<span style='color:#888'>(volume of E, m³)</span>")
        n1_lbl = QtWidgets.QLabel("n<sub>1</sub> &nbsp;<span style='color:#888'>(number of heights)</span>")
        n2_lbl = QtWidgets.QLabel("n<sub>2</sub> &nbsp;<span style='color:#888'>(subdivisions between heights)</span>")
        for lbl in [e_lbl, v_lbl, n1_lbl, n2_lbl]:
            lbl.setTextFormat(QtCore.Qt.RichText)

        self.txt_e  = QtWidgets.QLineEdit()
        self.txt_v  = QtWidgets.QLineEdit()
        self.txt_n1 = QtWidgets.QLineEdit()
        self.txt_n2 = QtWidgets.QLineEdit()
        self.txt_e.setPlaceholderText("e.g. 1240.0")
        self.txt_v.setPlaceholderText("e.g. 0.20e6")
        self.txt_n1.setPlaceholderText("e.g. 9")
        self.txt_n2.setPlaceholderText("e.g. 2")
        for t in [self.txt_e, self.txt_v, self.txt_n1, self.txt_n2]:
            t.setMinimumWidth(140)

        form.addWidget(e_lbl,  0, 0); form.addWidget(self.txt_e,  0, 1)
        form.addWidget(v_lbl,  0, 2); form.addWidget(self.txt_v,  0, 3)
        form.addWidget(n1_lbl, 1, 0); form.addWidget(self.txt_n1, 1, 1)
        form.addWidget(n2_lbl, 1, 2); form.addWidget(self.txt_n2, 1, 3)
        v.addLayout(form)

        # ----- Create Table button -----
        row = QtWidgets.QHBoxLayout()
        self.btn_create = QtWidgets.QPushButton("Create Table")
        self.btn_create.clicked.connect(self.on_create_table)
        self.btn_create.setToolTip(
            "Resize the data grid to n1+1 rows (header + n1 data rows).")
        row.addWidget(self.btn_create)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel(
            "<span style='color:#888; font-size:8pt'>"
            "Edit <b>height (m)</b> and <b>volume (m³)</b> in the table below. "
            "Heights must be strictly increasing."
            "</span>"))
        v.addLayout(row)

        # ----- Data grid (3 columns: Row#, height, volume) -----
        self.table = QtWidgets.QTableWidget(2, 3)
        self.table.setHorizontalHeaderLabels(["Row #", "height (m)", "volume (m³)"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.table.setAlternatingRowColors(True)
        # Header
        hh = self.table.horizontalHeader()
        for i in range(3):
            hh_item = self.table.horizontalHeaderItem(i)
            f = hh_item.font(); f.setBold(True); hh_item.setFont(f)
        # First row is locked as "Row 0" (the E, V point)
        for r in range(2):
            self._set_cell(r, 0, str(r))
            for c in [1, 2]:
                it = QtWidgets.QTableWidgetItem("")
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
                if r == 0:
                    it.setBackground(QtGui.QColor("#F4F1E8"))
                self.table.setItem(r, c, it)
        # Row 0: the (E, V) point - read-only display
        self.table.item(0, 1).setText("")  # filled from txt_e
        self.table.item(0, 2).setText("")  # filled from txt_v
        v.addWidget(self.table, 1)

        # ----- Live status line -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

        # ----- Bottom: Cancel / OK -----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("&Cancel")
        self.btn_cancel.clicked.connect(self.close)
        self.btn_ok = QtWidgets.QPushButton("&OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.on_ok)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        v.addLayout(btn_row)

        # If the state already has reservoir data, pre-populate the form
        if APP_STATE.reservoir_data is not None:
            self._populate_from_state()

    # ------------------------------------------------------------------
    #  FORM BEHAVIOUR  (mirrors the original VB6)
    # ------------------------------------------------------------------
    def _set_cell(self, r: int, c: int, text: str):
        it = QtWidgets.QTableWidgetItem(text)
        self.table.setItem(r, c, it)

    def on_create_table(self):
        """Resizes the grid to n1 + 1 rows, exactly like the original's
        Command2_Click.  Row 0 is the (E, V) point, rows 1..n1 are data."""
        n1_txt = self.txt_n1.text().strip()
        if not n1_txt.lstrip("-").isdigit():
            QtWidgets.QMessageBox.warning(self, "Invalid n1",
                "Please enter a number in the n1 field.")
            self.txt_n1.setFocus()
            return
        n1 = int(n1_txt) + 1   # VB does n1 = Val(Me.Text1(2).Text) + 1
        self.table.setRowCount(n1)
        # Re-fill row labels
        for r in range(n1):
            self._set_cell(r, 0, str(r))
        # Read E and V into row 0
        try:
            E = float(self.txt_e.text())
            V = float(self.txt_v.text())
        except ValueError:
            E = V = float("nan")
        self.table.item(0, 1).setText("" if E != E else f"{E:g}")
        self.table.item(0, 2).setText("" if V != V else f"{V:g}")
        # Lock row 0
        for c in [1, 2]:
            it = self.table.item(0, c)
            it.setFlags((it.flags() & ~QtCore.Qt.ItemIsEditable) | QtCore.Qt.ItemIsEnabled)
            it.setBackground(QtGui.QColor("#F4F1E8"))
        # Allow editing rows 1..n1-1
        for r in range(1, n1):
            for c in [1, 2]:
                it = self.table.item(r, c)
                if it is None:
                    it = QtWidgets.QTableWidgetItem("")
                    self.table.setItem(r, c, it)
                it.setFlags(it.flags() | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled)
        self.lbl_status.setText(f"Grid resized to {n1} rows.  "
                                 f"Fill height and volume columns for rows 1..{n1-1}.")

    def on_ok(self):
        """Mirrors Command1_Click(Index=0) in the original."""
        # 1. Validate n1, n2
        try:
            E = float(self.txt_e.text())
            V = float(self.txt_v.text())
            n1 = int(self.txt_n1.text()) + 1
            n2 = int(self.txt_n2.text())
        except ValueError as e:
            self.lbl_status.setText(
                f"<span style='color:#B8500A'>Invalid input: {e}</span>")
            return
        if n1 < 2:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: n1 must be >= 1</span>")
            return
        if n2 < 1:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: n2 must be >= 1</span>")
            return
        # 2. Validate grid is numeric
        for r in range(1, n1):
            for c in [1, 2]:
                item = self.table.item(r, c)
                if item is None:
                    self.lbl_status.setText(
                        f"<span style='color:#B8500A'>Invalid: row {r} col {c} is empty</span>")
                    return
                txt = item.text().strip()
                try:
                    float(txt)
                except ValueError:
                    self.lbl_status.setText(
                        f"<span style='color:#B8500A'>Invalid: row {r} col {c} is not numeric: '{txt}'</span>")
                    return
        # 3. Validate heights strictly increasing
        h_prev = E
        for r in range(1, n1):
            h = float(self.table.item(r, 1).text())
            if h <= h_prev:
                self.lbl_status.setText(
                    f"<span style='color:#B8500A'>Invalid: row {r} height {h} must be &gt; {h_prev}</span>")
                return
            h_prev = h
        # 4. Validate volumes strictly increasing
        v_prev = V
        for r in range(1, n1):
            vv = float(self.table.item(r, 2).text())
            if vv <= v_prev:
                self.lbl_status.setText(
                    f"<span style='color:#B8500A'>Invalid: row {r} volume {vv} must be &gt; {v_prev}</span>")
                return
            v_prev = vv

        # 5. Build the input grid (E, V) + (h_i, V_i) for i=1..n1-1
        h = [E] + [float(self.table.item(r, 1).text()) for r in range(1, n1)]
        Vv = [V] + [float(self.table.item(r, 2).text()) for r in range(1, n1)]

        # 6. Interpolate to the fine grid (the original's fillDatas algorithm)
        fine = cav.interpolate_reservoir_table(np.array(h), np.array(Vv), n2)

        # 7. Update APP_STATE
        APP_STATE.reservoir_data = cav.ReservoirTable(
            e=E, h=fine[:, 0], V=fine[:, 1])
        APP_STATE.reservoir = True

        # 8. Close
        self.lbl_status.setText(
            f"Saved {len(h)} input points -> {len(fine)} fine-grid points.  "
            f"Spillway Data menu is now enabled.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)

    def _populate_from_state(self):
        rd = APP_STATE.reservoir_data
        if rd is None:
            return
        n1_orig = sum(1 for h in rd.h if True)  # number of input points
        # Find the input points: they are the boundaries in fine grid
        # We use a heuristic: revert the interpolation to recover the input
        # E, V (just use h[0] and V[0] from the fine grid)
        self.txt_e.setText(f"{rd.h[0]:g}")
        self.txt_v.setText(f"{rd.V[0]:g}")
        n2 = 1   # we don't know n2 from the fine grid alone
        self.txt_n1.setText(str(len(rd.h) - 1))
        self.txt_n2.setText(str(n2))
        self.on_create_table()
        # Fill the table from the fine grid (best-effort)
        for r in range(min(self.table.rowCount(), len(rd.h))):
            self.table.item(r, 1).setText(f"{rd.h[r]:g}")
            self.table.item(r, 2).setText(f"{rd.V[r]:g}")
        self.lbl_status.setText(
            f"Loaded from project state: {len(rd.h)} fine-grid points.")
