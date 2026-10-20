"""
ui/forms/constp_form.py - CONSTP (Controlled Pressure) form.

Wired to em_constp.compute_constp() for the sinusoidal / triangular
piezometric pressure distributions.
"""
from __future__ import annotations
import os
import math
from PySide6 import QtCore, QtWidgets
from ui.charts.matplotlib_widget import MplCanvas
from ui import mdi_main
from em_data import read_geometry_file
from em_constp import compute_constp


class CONSTPForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CONSTP - Controlled Pressure Spillway")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn_sin = QtWidgets.QPushButton("Open GLENSD (sinusoidal)...")
        btn_sin.clicked.connect(lambda: self._open("S"))
        btn_tri = QtWidgets.QPushButton("Open GLENTD (triangular)...")
        btn_tri.clicked.connect(lambda: self._open("T"))
        h.addWidget(btn_sin); h.addWidget(btn_tri); h.addStretch(1)
        layout.addLayout(h)

        # Options
        gb_opt = QtWidgets.QGroupBox("Options")
        gl = QtWidgets.QFormLayout(gb_opt)
        self.dist = QtWidgets.QComboBox()
        self.dist.addItems(["Sinusoidal (S)", "Triangular (T)"])
        self.deflection = QtWidgets.QDoubleSpinBox()
        self.deflection.setRange(0, 90)
        self.deflection.setValue(20.0)
        self.deflection.setSuffix(" deg")
        self.radius_factor = QtWidgets.QDoubleSpinBox()
        self.radius_factor.setRange(0.1, 10.0)
        self.radius_factor.setValue(1.0)
        gl.addRow("Distribution:", self.dist)
        gl.addRow("Deflection angle:", self.deflection)
        gl.addRow("Radius factor:", self.radius_factor)
        layout.addWidget(gb_opt)

        btn_compute = QtWidgets.QPushButton("Compute")
        btn_compute.clicked.connect(self._compute)
        layout.addWidget(btn_compute)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["STA", "Invert", "Width", "R1", "R2", "R_curv"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        splitter.addWidget(self.table)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.canvas = MplCanvas(width=7, height=5, dpi=100)
        rv.addWidget(self.canvas)
        self.results = QtWidgets.QTextEdit()
        self.results.setReadOnly(True)
        self.results.setMaximumHeight(100)
        rv.addWidget(self.results)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

    def _open(self, kind: str):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open controlled-pressure file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Pressure files (GLENSD GLENTD);;All files (*)")
        if not path: return
        try:
            g = read_geometry_file(path)
            mdi_main.APP_STATE.geometry = g
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            # Set distribution
            self.dist.setCurrentIndex(0 if kind == "S" else 1)
            self._show_table(g)
            self._compute()
        except Exception as e:
            self.status.setText(f"Error: {e}")

    def _show_table(self, g):
        self.table.setRowCount(len(g.stations))
        for i, s in enumerate(g.stations):
            for j, v in enumerate([s.sta, s.invert, s.width, s.r1, s.r2, s.rad_curv]):
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(f"{v:.3f}"))

    def _compute(self):
        g = mdi_main.APP_STATE.geometry
        if g is None:
            self.status.setText("Open a geometry file first.")
            return
        distribution = "S" if self.dist.currentIndex() == 0 else "T"
        try:
            res = compute_constp(
                g,
                distribution=distribution,
                deflection_angle_deg=self.deflection.value(),
                radius_factor=self.radius_factor.value(),
            )
            if not res.success:
                self.status.setText(f"Error: {res.error_message}")
                return
            self._show_table(g)
            self._plot(g, res)
            self.results.setPlainText(
                f"Distribution: {distribution} ({'sinusoidal' if distribution == 'S' else 'triangular'})\n"
                f"Radius of curvature: {res.radius_of_curvature:.1f} m\n"
                f"Deflection angle: {res.deflection_angle_deg:.1f} deg\n"
                f"Arc length: {res.arc_length:.1f} m\n"
                f"Max piez head: {res.max_piez_head:.3f} m\n"
                f"Min piez head: {res.min_piez_head:.3f} m"
            )
            self.status.setText(f"CONSTP computed: R={res.radius_of_curvature:.1f} m, max piez={res.max_piez_head:.3f} m")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.setText(f"Error: {e}")

    def _plot(self, g, res):
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        stas = [s.sta for s in g.stations]
        invs = [s.invert for s in g.stations]
        ax.plot(stas, invs, 'k-', linewidth=2, label='Invert')

        # Plot the piezometric profile as a deviation from the invert
        theta = [p.theta_deg for p in res.points]
        s_vals = [p.s for p in res.points]
        # s is arc length; convert to station by adding s_up
        s_stas = [res.upstream_station + s for s in s_vals]
        piezo = [res.upstream_elev - p.piez_head for p in res.points]
        ax.plot(s_stas, piezo, 'b--', linewidth=1.5,
                label=f'Piez head ({res.distribution}, R={res.radius_of_curvature:.1f} m)')

        ax.set_xlabel('Station (m)')
        ax.set_ylabel('Elevation (m)')
        ax.set_title(f'CONSTP - {res.distribution} pressure distribution\n'
                     f'Q = {res.Q} cms, deflection = {res.deflection_angle_deg:.1f} deg')
        ax.grid(True, alpha=0.3)
        ax.legend()
        self.canvas.draw()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = CONSTPForm()
    w.show()
    sys.exit(app.exec())
