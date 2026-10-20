"""
ui/forms/ecavno_form.py - ECAVNO (Equal Cavitation Number) form.

Wired to em_ecavno.design_spillway() for the iterative equal-sigma design.
"""
from __future__ import annotations
import os
from PySide6 import QtCore, QtWidgets
from ui.charts.matplotlib_widget import MplCanvas
from ui import mdi_main
from em_data import read_ecn_input
from em_ecavno import design_spillway


class ECAVNOForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ECAVNO - Equal Cavitation Number")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn = QtWidgets.QPushButton("Open ECNDAT + GLENECN...")
        btn.clicked.connect(self._open)
        btn_design = QtWidgets.QPushButton("Design spillway")
        btn_design.clicked.connect(self._design)
        h.addWidget(btn)
        h.addWidget(btn_design)
        h.addStretch(1)
        layout.addLayout(h)

        # Target sigma input
        gb = QtWidgets.QGroupBox("Target cavitation index")
        gl = QtWidgets.QFormLayout(gb)
        self.sigma = QtWidgets.QDoubleSpinBox()
        self.sigma.setRange(0.01, 1.0)
        self.sigma.setDecimals(4)
        self.sigma.setValue(0.20)
        self.centrifugal = QtWidgets.QCheckBox("Include centrifugal correction (rotation assumption)")
        gl.addRow("sigma_target:", self.sigma)
        gl.addRow("", self.centrifugal)
        layout.addWidget(gb)

        # Problem definition
        gb2 = QtWidgets.QGroupBox("Problem definition (from ECNDAT)")
        gl2 = QtWidgets.QFormLayout(gb2)
        self.lbl = {
            "title": QtWidgets.QLabel("(not loaded)"),
            "q": QtWidgets.QLabel("—"),
            "y0": QtWidgets.QLabel("—"),
            "reservoir": QtWidgets.QLabel("—"),
            "assumption": QtWidgets.QLabel("—"),
        }
        for k, lbl in self.lbl.items():
            gl2.addRow(k.replace("_", " ").title() + ":", lbl)
        layout.addWidget(gb2)

        # Station table
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["STA", "z_user", "z_designed", "depth", "V", "sigma", "achieved"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        # Chart
        self.canvas = MplCanvas(width=8, height=4, dpi=100)
        layout.addWidget(self.canvas)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

    def _open(self):
        dat_dir = mdi_main.APP_STATE.last_data_dir or os.path.join(
            os.path.dirname(mdi_main.ROOT), "sample_data", "DATA")
        ecn_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open ECNDAT (problem definition)", dat_dir, "ECNDAT")
        if not ecn_path: return
        glen_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open GLENECN (station geometry)", dat_dir, "GLENECN")
        if not glen_path: return
        try:
            e = read_ecn_input(ecn_path, glen_path)
            mdi_main.APP_STATE.ecn_input = e
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(ecn_path)
            self._show_problem(e)
        except Exception as e:
            self.status.setText(f"Error: {e}")

    def _show_problem(self, e):
        self.lbl["title"].setText(e.title)
        self.lbl["q"].setText(f"{e.q:.3f} m^3/s" if e.is_si else f"{e.q:.3f} cfs")
        self.lbl["y0"].setText(f"{e.y0:.4f} m" if e.is_si else f"{e.y0:.4f} ft")
        self.lbl["reservoir"].setText(f"{e.reservoir_elev:.3f} m" if e.is_si else f"{e.reservoir_elev:.3f} ft")
        self.lbl["assumption"].setText(
            "Potential flow (irrotational)" if e.assumption == "N" else "Solid body rotation")
        # Pre-populate the table with the input invert
        self.table.setRowCount(len(e.stations))
        for i, s in enumerate(e.stations):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(f"{s.sta:.3f}"))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{s.invert:.3f}"))
        self.status.setText(f"Loaded {len(e.stations)} stations.")

    def _design(self):
        e = mdi_main.APP_STATE.ecn_input
        if e is None:
            self.status.setText("Open ECNDAT + GLENECN first.")
            return
        try:
            res = design_spillway(
                e, sigma_target=self.sigma.value(),
                include_centrifugal=self.centrifugal.isChecked(),
            )
            if not res.success:
                self.status.setText(f"Error: {res.error_message}")
                return
            # Populate table
            self.table.setRowCount(len(res.rows))
            for i, r in enumerate(res.rows):
                self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(f"{r['sta']:.3f}"))
                self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{r['invert_orig']:.3f}"))
                self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{r['invert_designed']:.3f}"))
                self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(f"{r['depth']:.3f}"))
                self.table.setItem(i, 4, QtWidgets.QTableWidgetItem(f"{r['velocity']:.2f}"))
                sigma_disp = f"{r['sigma_with_user_invert']:.3f}" if r['sigma_with_user_invert'] < 100 else "inf"
                self.table.setItem(i, 5, QtWidgets.QTableWidgetItem(sigma_disp))
                self.table.setItem(i, 6, QtWidgets.QTableWidgetItem("Y" if r['target_achieved'] else "N"))
            # Plot: invert profile and piezometric sigma
            self._plot(res)
            n_achieved = sum(1 for r in res.rows if r['target_achieved'])
            self.status.setText(
                f"Designed {len(res.rows)} stations. "
                f"Target sigma = {self.sigma.value():.3f}, "
                f"{n_achieved}/{len(res.rows)} achieved within 10% tolerance.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.setText(f"Error: {e}")

    def _plot(self, res):
        self.canvas.fig.clear()
        ax1 = self.canvas.fig.add_subplot(211)
        stas = [r['sta'] for r in res.rows]
        z_user = [r['invert_orig'] for r in res.rows]
        z_des = [r['invert_designed'] for r in res.rows]
        ax1.plot(stas, z_user, 'k-', linewidth=2, label='User invert')
        ax1.plot(stas, z_des, 'b--', linewidth=1.5, label='Designed invert')
        ax1.set_ylabel('Elevation (m)')
        ax1.set_title('ECAVNO: Spillway Profile (user vs designed)')
        ax1.legend(fontsize=9)
        ax1.grid(True, alpha=0.3)

        ax2 = self.canvas.fig.add_subplot(212)
        sigmas = [r['sigma_with_user_invert'] for r in res.rows
                  if 0 < r['sigma_with_user_invert'] < 10]
        sig_sta = [r['sta'] for r in res.rows
                   if 0 < r['sigma_with_user_invert'] < 10]
        if sigmas:
            ax2.plot(sig_sta, sigmas, 'r-', linewidth=2, label='sigma')
        ax2.axhline(self.sigma.value(), color='b', linestyle=':', label=f'target = {self.sigma.value():.3f}')
        ax2.set_xlabel('Station (m)')
        ax2.set_ylabel('Cavitation index sigma')
        ax2.set_title('Sigma along designed profile')
        ax2.legend(fontsize=9)
        ax2.grid(True, alpha=0.3)
        self.canvas.fig.tight_layout()
        self.canvas.draw()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = ECAVNOForm()
    w.show()
    sys.exit(app.exec())
