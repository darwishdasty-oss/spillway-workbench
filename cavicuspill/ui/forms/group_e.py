"""
ui/forms/group_e.py - The 6 unported sub-grid forms from the original Cavicuspill
VB6 source.  Each of these was a sub-grid window in the original Cavituspill
MDI shell, showing the underlying data table that drove the main calculation.

This module ports all 6 forms:
    E1. ReservoirPropertiesGridForm
    E2. InFlowDataGridForm
    E3. OutFlowDataGridForm
    E4. SpillWayDataGridForm (with type selector)
    E5. ProfileDataForm
    E6. OutflowDiagramForm
"""
from __future__ import annotations
import os
from typing import List, Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

import cavicuspill as cav


# =============================================================================
# E1. ReservoirPropertiesGridForm
# =============================================================================
class ReservoirPropertiesGridForm(QtWidgets.QMdiSubWindow):
    """Elevation-Volume table for the reservoir.

    Shows the user's input table as a sortable QTableWidget.
    The 'Refresh' button interpolates the table to a finer grid using
    the original `fillDatas` algorithm from ReservoirProperties.frm.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("E1. Reservoir Properties Grid")
        self.resize(620, 460)
        self._build_ui()

    def _build_ui(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)

        # Header
        h = QtWidgets.QLabel("<b>Reservoir Elevation-Volume Table</b>")
        h.setStyleSheet("font-size: 13px;")
        v.addWidget(h)

        # Sub-controls
        ctrl_h = QtWidgets.QHBoxLayout()
        ctrl_h.addWidget(QtWidgets.QLabel("Subdivisions per interval (n2):"))
        self.spin_n2 = QtWidgets.QSpinBox()
        self.spin_n2.setRange(1, 100)
        self.spin_n2.setValue(10)
        ctrl_h.addWidget(self.spin_n2)
        btn_refresh = QtWidgets.QPushButton("Interpolate (FillD atas)")
        btn_refresh.clicked.connect(self._on_refresh)
        ctrl_h.addWidget(btn_refresh)
        btn_print = QtWidgets.QPushButton("&Print")
        btn_print.clicked.connect(self._on_print)
        ctrl_h.addWidget(btn_print)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.clicked.connect(self.close)
        ctrl_h.addWidget(btn_close)
        ctrl_h.addStretch(1)
        v.addLayout(ctrl_h)

        # Table
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Row#", "Height (m)", "Volume (m^3)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        # Summary
        self.summary = QtWidgets.QLabel("No data loaded. Use Reservoir Properties form first.")
        self.summary.setStyleSheet("color: gray; font-style: italic;")
        v.addWidget(self.summary)

        self.setWidget(w)

    def _load_from_state(self):
        res = cav.APP_STATE.reservoir_data if hasattr(cav, 'APP_STATE') else None
        from ui.mdi_main import APP_STATE
        res = APP_STATE.reservoir_data
        if res is None or len(res.h) == 0:
            self.summary.setText("No reservoir data loaded. Fill in Reservoir Properties form first.")
            return
        self._populate_table(res.h, res.V)

    def _populate_table(self, h, V):
        self.table.setRowCount(len(h))
        for i in range(len(h)):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{h[i]:.3f}"))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{V[i]:.3f}"))
        self.summary.setText(f"{len(h)} rows (input).")

    def _on_refresh(self):
        from ui.mdi_main import APP_STATE
        res = APP_STATE.reservoir_data
        if res is None or len(res.h) < 2:
            self.summary.setText("Need >= 2 input points.")
            return
        n2 = self.spin_n2.value()
        fine = cav.interpolate_reservoir_table(res.h, res.V, n2)
        self._populate_table(fine[:, 0], fine[:, 1])
        self.summary.setText(
            f"Interpolated to {len(fine)} rows (n2={n2}).  "
            f"h: {fine[0, 0]:.2f}..{fine[-1, 0]:.2f} m,  "
            f"V: {fine[0, 1]:.0f}..{fine[-1, 1]:.0f} m^3.")

    def _on_print(self):
        printer = QtGui.QTextDocument()
        html = "<h2>Reservoir Properties</h2><table border='1' cellpadding='4'>"
        html += "<tr><th>Row</th><th>Height (m)</th><th>Volume (m^3)</th></tr>"
        for i in range(self.table.rowCount()):
            html += "<tr>"
            for c in range(3):
                html += f"<td>{self.table.item(i, c).text()}</td>"
            html += "</tr>"
        html += "</table>"
        printer.setHtml(html)
        dlg = QtWidgets.QPrintDialog()
        if dlg.exec() == QtWidgets.QPrintDialog.Accepted:
            dlg.printer().newPage()
            printer.print_(dlg.printer())

    def showEvent(self, event):
        super().showEvent(event)
        self._load_from_state()


# =============================================================================
# E2. InFlowDataGridForm
# =============================================================================
class InFlowDataGridForm(QtWidgets.QMdiSubWindow):
    """Inflow hydrograph grid: time (h) vs Q (m^3/s)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("E2. Inflow Data Grid")
        self.resize(560, 460)
        self._build_ui()

    def _build_ui(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        h = QtWidgets.QLabel("<b>Inflow Hydrograph</b>")
        h.setStyleSheet("font-size: 13px;")
        v.addWidget(h)

        ctrl = QtWidgets.QHBoxLayout()
        btn_print = QtWidgets.QPushButton("&Print")
        btn_print.clicked.connect(self._on_print)
        ctrl.addWidget(btn_print)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.clicked.connect(self.close)
        ctrl.addWidget(btn_close)
        ctrl.addStretch(1)
        v.addLayout(ctrl)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Row#", "Time (hours)", "Q (m^3/s)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        self.summary = QtWidgets.QLabel("No inflow data loaded.")
        self.summary.setStyleSheet("color: gray; font-style: italic;")
        v.addWidget(self.summary)

        self.setWidget(w)

    def _load_from_state(self):
        from ui.mdi_main import APP_STATE
        inflow = APP_STATE.inflow
        if inflow is None or len(inflow.t_h) == 0:
            self.summary.setText("No inflow data loaded.")
            return
        self.table.setRowCount(len(inflow.t_h))
        for i in range(len(inflow.t_h)):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{inflow.t_h[i]:.3f}"))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{inflow.Q[i]:.3f}"))
        peak_idx = int(np.argmax(inflow.Q))
        self.summary.setText(
            f"{len(inflow.t_h)} points.  Peak Q = {inflow.Q[peak_idx]:.2f} m^3/s "
            f"at t = {inflow.t_h[peak_idx]:.2f} h.  "
            f"Volume = {np.trapezoid(inflow.Q, inflow.t_h) * 3600:.0f} m^3."
        )

    def _on_print(self):
        printer = QtGui.QTextDocument()
        html = "<h2>Inflow Hydrograph</h2><table border='1' cellpadding='4'>"
        html += "<tr><th>Row</th><th>Time (h)</th><th>Q (m^3/s)</th></tr>"
        for i in range(self.table.rowCount()):
            html += "<tr>"
            for c in range(3):
                html += f"<td>{self.table.item(i, c).text()}</td>"
            html += "</tr>"
        html += "</table>"
        printer.setHtml(html)
        dlg = QtWidgets.QPrintDialog()
        if dlg.exec() == QtWidgets.QPrintDialog.Accepted:
            printer.print_(dlg.printer())

    def showEvent(self, event):
        super().showEvent(event)
        self._load_from_state()


# =============================================================================
# E3. OutFlowDataGridForm
# =============================================================================
class OutFlowDataGridForm(QtWidgets.QMdiSubWindow):
    """Outflow iteration grid showing the Modified Puls routing calculation.

    Columns: Row#, I1+I2 m^3/s, 2S/dt-O m^3/s, 2S/dt+O m^3/s, Q(out) m^3/s
    This is the table generated by the flood-routing iteration in Outflow.frm.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("E3. Outflow Data Grid")
        self.resize(720, 480)
        self._build_ui()

    def _build_ui(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        h = QtWidgets.QLabel("<b>Outflow Routing Iteration (Modified Puls)</b>")
        h.setStyleSheet("font-size: 13px;")
        v.addWidget(h)

        ctrl = QtWidgets.QHBoxLayout()
        btn_print = QtWidgets.QPushButton("&Print")
        btn_print.clicked.connect(self._on_print)
        ctrl.addWidget(btn_print)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.clicked.connect(self.close)
        ctrl.addWidget(btn_close)
        ctrl.addStretch(1)
        v.addLayout(ctrl)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Row#", "I1+I2 (m^3/s)", "2S/dt-O (m^3/s)",
            "2S/dt+O (m^3/s)", "Q(out) (m^3/s)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        self.summary = QtWidgets.QLabel(
            "No outflow data loaded.  Run Flood Routing > 4. Calculate Outflow first.")
        self.summary.setStyleSheet("color: gray; font-style: italic;")
        v.addWidget(self.summary)

        self.setWidget(w)

    def _load_from_state(self):
        from ui.mdi_main import APP_STATE
        surface = APP_STATE.surface_profile
        if surface is None or 'routing_table' not in surface:
            self.summary.setText("No outflow routing data.  Run the routing calculation first.")
            return
        table = surface['routing_table']
        self.table.setRowCount(len(table))
        for i, row in enumerate(table):
            for c, val in enumerate(row):
                self.table.setItem(i, c, QtWidgets.QTableWidgetItem(
                    f"{val:.3f}" if isinstance(val, (int, float)) else str(val)))
        # Summary
        if len(table) > 0:
            peak_q = max((r[4] for r in table if isinstance(r[4], (int, float))), default=0)
            self.summary.setText(
                f"{len(table)} time steps.  Peak outflow = {peak_q:.2f} m^3/s.")

    def _on_print(self):
        printer = QtGui.QTextDocument()
        html = "<h2>Outflow Routing</h2><table border='1' cellpadding='4'>"
        headers = ["Row#", "I1+I2", "2S/dt-O", "2S/dt+O", "Q(out)"]
        html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        for i in range(self.table.rowCount()):
            html += "<tr>"
            for c in range(5):
                html += f"<td>{self.table.item(i, c).text()}</td>"
            html += "</tr>"
        html += "</table>"
        printer.setHtml(html)
        dlg = QtWidgets.QPrintDialog()
        if dlg.exec() == QtWidgets.QPrintDialog.Accepted:
            printer.print_(dlg.printer())

    def showEvent(self, event):
        super().showEvent(event)
        self._load_from_state()


# =============================================================================
# E4. SpillWayDataGridForm
# =============================================================================
class SpillWayDataGridForm(QtWidgets.QMdiSubWindow):
    """Spillway storage-discharge table with a list selector for spillway length.

    The original VB6 had a list of candidate spillway lengths (L_min..L_max
    in increments of b).  Selecting one shows the Q(h) table for that L.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("E4. Spillway Data Grid")
        self.resize(720, 520)
        self._L_list: List[float] = []
        self._build_ui()

    def _build_ui(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        h = QtWidgets.QLabel("<b>Spillway Storage-Discharge (Q vs h)</b>")
        h.setStyleSheet("font-size: 13px;")
        v.addWidget(h)

        # Top: list selector
        sel_h = QtWidgets.QHBoxLayout()
        sel_h.addWidget(QtWidgets.QLabel("Select  (  L )"))
        self.list_L = QtWidgets.QListWidget()
        self.list_L.setMaximumWidth(120)
        self.list_L.currentRowChanged.connect(self._on_L_changed)
        sel_h.addWidget(self.list_L)
        v.addLayout(sel_h)

        # The grid
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Row#", "Height (m)", "Q (m^3/s)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        # Bottom: print/close
        ctrl = QtWidgets.QHBoxLayout()
        btn_print = QtWidgets.QPushButton("&Print")
        btn_print.clicked.connect(self._on_print)
        ctrl.addWidget(btn_print)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.clicked.connect(self.close)
        ctrl.addWidget(btn_close)
        ctrl.addStretch(1)
        v.addLayout(ctrl)

        self.summary = QtWidgets.QLabel("No spillway data loaded.  Run Spillway Data form first.")
        self.summary.setStyleSheet("color: gray; font-style: italic;")
        v.addWidget(self.summary)

        self.setWidget(w)

    def _load_from_state(self):
        from ui.mdi_main import APP_STATE
        res = APP_STATE.reservoir_data
        sw = APP_STATE.spillway_cfg
        if res is None or sw is None or len(res.h) == 0:
            self.summary.setText("No reservoir / spillway data loaded.")
            return
        # Build the list of L values
        self._L_list = []
        Ln = int((sw.L_max - sw.L_min) / sw.b) + 1
        for i in range(1, Ln + 1):
            L = (i - 1) * sw.b + sw.L_min
            if L > sw.L_max:
                L = sw.L_max
            self._L_list.append(L)
        self.list_L.clear()
        for L in self._L_list:
            self.list_L.addItem(f"L = {L:.1f} m")
        if self._L_list:
            self.list_L.setCurrentRow(0)
        self.summary.setText(
            f"{len(self._L_list)} spillway lengths, {len(res.h)} elevations each.  "
            f"L range: {sw.L_min:.1f} .. {sw.L_max:.1f} m, step {sw.b:.1f} m.")

    def _on_L_changed(self, row):
        if row < 0 or row >= len(self._L_list):
            return
        from ui.mdi_main import APP_STATE
        res = APP_STATE.reservoir_data
        sw = APP_STATE.spillway_cfg
        if res is None or sw is None:
            return
        L = self._L_list[row]
        Q = L * sw.c * np.maximum(res.h - res.e, 0.0) ** 1.5
        self.table.setRowCount(len(res.h))
        for i in range(len(res.h)):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{res.h[i]:.3f}"))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{Q[i]:.3f}"))

    def _on_print(self):
        printer = QtGui.QTextDocument()
        html = "<h2>Spillway Q(h) Table</h2>"
        if self.list_L.currentRow() >= 0:
            html += f"<p>Selected: L = {self._L_list[self.list_L.currentRow()]:.1f} m</p>"
        html += "<table border='1' cellpadding='4'>"
        html += "<tr><th>Row</th><th>Height (m)</th><th>Q (m^3/s)</th></tr>"
        for i in range(self.table.rowCount()):
            html += "<tr>"
            for c in range(3):
                html += f"<td>{self.table.item(i, c).text()}</td>"
            html += "</tr>"
        html += "</table>"
        printer.setHtml(html)
        dlg = QtWidgets.QPrintDialog()
        if dlg.exec() == QtWidgets.QPrintDialog.Accepted:
            printer.print_(dlg.printer())

    def showEvent(self, event):
        super().showEvent(event)
        self._load_from_state()


# =============================================================================
# E5. ProfileDataForm
# =============================================================================
class ProfileDataForm(QtWidgets.QMdiSubWindow):
    """Profile data editor showing all spillway profile parameters.

    Fields from the original VB6:
        Slope Of Upstream (CD)
        L  (Distance from crest to toe)
        unit
    Plus the full set of profile geometry inputs.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("E5. Profile Data")
        self.resize(680, 540)
        self._build_ui()

    def _build_ui(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        h = QtWidgets.QLabel("<b>Spillway Profile Data</b>")
        h.setStyleSheet("font-size: 13px;")
        v.addWidget(h)

        # Form layout
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        self.edit_slope_up = QtWidgets.QLineEdit("0.0")
        form.addRow("Slope Of Upstream (CD):", self.edit_slope_up)
        self.edit_L = QtWidgets.QLineEdit("0.0")
        form.addRow("L (Distance from crest to toe):", self.edit_L)
        self.combo_unit = QtWidgets.QComboBox()
        self.combo_unit.addItems(["m", "ft"])
        form.addRow("Unit:", self.combo_unit)
        # Separator
        form.addRow(QtWidgets.QLabel("--- Crest Geometry ---"))
        self.edit_P = QtWidgets.QLineEdit("0.0")
        form.addRow("P (Crest height above floor):", self.edit_P)
        self.edit_H = QtWidgets.QLineEdit("0.0")
        form.addRow("H (Design head):", self.edit_H)
        self.edit_Lc = QtWidgets.QLineEdit("0.0")
        form.addRow("Lc (Crest length):", self.edit_Lc)
        v.addLayout(form)

        # OK / Cancel
        btn_h = QtWidgets.QHBoxLayout()
        btn_ok = QtWidgets.QPushButton("&OK")
        btn_ok.clicked.connect(self._on_ok)
        btn_h.addWidget(btn_ok)
        btn_cancel = QtWidgets.QPushButton("&Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_h.addWidget(btn_cancel)
        btn_h.addStretch(1)
        v.addLayout(btn_h)

        # Help
        help_lbl = QtWidgets.QLabel(
            "<i>Slope of upstream face CD; L is the projected length of the "
            "spillway from crest to toe; P is the crest height; H is the "
            "design head; Lc is the crest length.</i>")
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #555;")
        v.addWidget(help_lbl)
        v.addStretch(1)

        self.setWidget(w)

    def _on_ok(self):
        from ui.mdi_main import APP_STATE
        try:
            data = {
                "slope_upstream": float(self.edit_slope_up.text()),
                "L_crest_to_toe": float(self.edit_L.text()),
                "unit": self.combo_unit.currentText(),
                "P_crest_height": float(self.edit_P.text()),
                "H_design_head": float(self.edit_H.text()),
                "Lc_crest_length": float(self.edit_Lc.text()),
            }
            APP_STATE.profile_data = data
            APP_STATE.profileData = True
            self.close()
        except ValueError:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        from ui.mdi_main import APP_STATE
        d = getattr(APP_STATE, 'profile_data', None) or {}
        self.edit_slope_up.setText(str(d.get("slope_upstream", 0.0)))
        self.edit_L.setText(str(d.get("L_crest_to_toe", 0.0)))
        idx = self.combo_unit.findText(d.get("unit", "m"))
        if idx >= 0:
            self.combo_unit.setCurrentIndex(idx)
        self.edit_P.setText(str(d.get("P_crest_height", 0.0)))
        self.edit_H.setText(str(d.get("H_design_head", 0.0)))
        self.edit_Lc.setText(str(d.get("Lc_crest_length", 0.0)))


# =============================================================================
# E6. OutflowDiagramForm
# =============================================================================
class OutflowDiagramForm(QtWidgets.QMdiSubWindow):
    """Outflow hydrograph chart, plotted with matplotlib.

    Shows the inflow vs outflow vs storage over the routing period.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("E6. Outflow Diagram")
        self.resize(720, 480)
        self._build_ui()

    def _build_ui(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)

        h = QtWidgets.QLabel("<b>Outflow Hydrograph</b>")
        h.setStyleSheet("font-size: 13px;")
        v.addWidget(h)

        # The chart will be a simple matplotlib FigureCanvas
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self.fig = Figure(figsize=(6, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)
        v.addWidget(self.canvas)

        # OK / Cancel
        btn_h = QtWidgets.QHBoxLayout()
        btn_ok = QtWidgets.QPushButton("&OK")
        btn_ok.clicked.connect(self.close)
        btn_h.addWidget(btn_ok)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.clicked.connect(self.close)
        btn_h.addWidget(btn_close)
        btn_h.addStretch(1)
        v.addLayout(btn_h)

        self.setWidget(w)

    def showEvent(self, event):
        super().showEvent(event)
        self._redraw()

    def _redraw(self):
        self.fig.clear()
        from ui.mdi_main import APP_STATE
        ax = self.fig.add_subplot(111)
        plotted = False
        if APP_STATE.inflow is not None and len(APP_STATE.inflow.t_h) > 0:
            ax.plot(APP_STATE.inflow.t_h, APP_STATE.inflow.Q, "b-",
                    lw=1.5, label="Inflow")
            plotted = True
        surf = APP_STATE.surface_profile
        if surf and "routing_table" in surf and len(surf["routing_table"]) > 0:
            t = [r[0] for r in surf["routing_table"]]
            qout = [r[4] for r in surf["routing_table"]]
            ax.plot(t, qout, "r-", lw=1.5, label="Outflow")
            plotted = True
        ax.set_xlabel("Time (hours)")
        ax.set_ylabel("Q (m^3/s)")
        ax.set_title("Flood Routing: Inflow vs Outflow")
        if plotted:
            ax.legend(loc="best")
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, "No routing data.  Run Flood Routing > 4. Calculate Outflow first.",
                    transform=ax.transAxes, ha="center", va="center", fontsize=11)
            ax.set_xticks([]); ax.set_yticks([])
        self.canvas.draw()


# =============================================================================
# Module-level registry
# =============================================================================

GROUP_E_FORMS = {
    "e1": ("E1. Reservoir Properties Grid", ReservoirPropertiesGridForm),
    "e2": ("E2. Inflow Data Grid", InFlowDataGridForm),
    "e3": ("E3. Outflow Data Grid", OutFlowDataGridForm),
    "e4": ("E4. Spillway Data Grid", SpillWayDataGridForm),
    "e5": ("E5. Profile Data", ProfileDataForm),
    "e6": ("E6. Outflow Diagram", OutflowDiagramForm),
}
