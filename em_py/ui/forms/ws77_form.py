"""
ui/forms/ws77_form.py - WS77 (Water Surface Profile) form.

Wired to em_ws77.compute_profile() for the full standard-step + boundary-layer
+ cavitation-index algorithm.
"""
from __future__ import annotations
import os
from PySide6 import QtCore, QtGui, QtWidgets
from ui.charts.matplotlib_widget import MplCanvas
from ui import mdi_main
from em_data import read_geometry_file, read_ws_output
from em_ws77 import compute_profile


class WS77Form(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WS77 - Water Surface Profile")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        self.file_edit = QtWidgets.QLineEdit()
        btn_pick = QtWidgets.QPushButton("Open GLENIN / SPWY...")
        btn_pick.clicked.connect(self._pick)
        btn_run = QtWidgets.QPushButton("Run WS77")
        btn_run.clicked.connect(self._run)
        h.addWidget(QtWidgets.QLabel("Geometry:"))
        h.addWidget(self.file_edit, 1)
        h.addWidget(btn_pick)
        h.addWidget(btn_run)
        layout.addLayout(h)

        # EGL calibration (optional)
        gb_cal = QtWidgets.QGroupBox("Calibration (optional)")
        gbl = QtWidgets.QHBoxLayout(gb_cal)
        gbl.addWidget(QtWidgets.QLabel("EGL at start of boundary layer (m):"))
        self.egl_cal = QtWidgets.QLineEdit()
        self.egl_cal.setPlaceholderText("(auto from geometry if blank)")
        gbl.addWidget(self.egl_cal)
        gbl.addStretch(1)
        layout.addWidget(gb_cal)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "STA", "Invert", "Width", "Slope", "R1", "CL_H", "R_curv", "Rough"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        splitter.addWidget(self.table)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.canvas = MplCanvas(width=7, height=5, dpi=100)
        rv.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

    def _pick(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open geometry file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Geometry files (GLENIN SPWY *.INP);;All files (*)")
        if path:
            self.file_edit.setText(path)
            self._load_into_table(path)

    def _load_into_table(self, path):
        try:
            g = read_geometry_file(path)
            mdi_main.APP_STATE.geometry = g
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
        except Exception as e:
            self.status.setText(f"Error: {e}")
            return
        self.table.setRowCount(len(g.stations))
        for i, s in enumerate(g.stations):
            for j, v in enumerate([s.sta, s.invert, s.width, s.side_slope,
                                    s.r1, s.cl_height, s.rad_curv, s.roughness]):
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(f"{v:.3f}"))
        self.status.setText(f"Loaded {len(g.stations)} stations from {path}")

    def _run(self):
        g = mdi_main.APP_STATE.geometry
        if g is None:
            self.status.setText("Open a geometry file first.")
            return
        egl = None
        if self.egl_cal.text().strip():
            try:
                egl = float(self.egl_cal.text())
            except ValueError:
                self.status.setText("Invalid EGL value")
                return
        try:
            res = compute_profile(g, egl_calibration=egl)
            if not res.success:
                self.status.setText(f"Error: {res.error_message}")
                return
            self._plot_results(g, res)
            n_achieved = sum(1 for r in res.rows if 0 < r['sigma'] < 1.0)
            self.status.setText(
                f"WS77 completed: {len(res.rows)} stations computed, "
                f"EGL_initial = {res.egl_initial:.3f} m, "
                f"{n_achieved} stations with 0 < sigma < 1")
            mdi_main.APP_STATE.ws_output = res
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.setText(f"Error: {e}")

    def _plot_results(self, g, res):
        self.canvas.fig.clear()
        # 2 subplots: water surface profile + cavitation
        ax1 = self.canvas.fig.add_subplot(211)
        sta = [r['sta'] for r in res.rows]
        inv = [r['invert'] for r in res.rows]
        wse = [r['invert'] + r['depth'] for r in res.rows]
        egl = [r['egl'] for r in res.rows]
        ax1.plot(sta, inv, 'k-', linewidth=2, label='Invert')
        ax1.plot(sta, wse, 'b-', linewidth=1.5, label='Water surface')
        ax1.plot(sta, egl, 'r--', linewidth=1, label='EGL', alpha=0.6)
        ax1.fill_between(sta, inv, wse, color='cyan', alpha=0.2)
        ax1.set_ylabel('Elevation (m)')
        ax1.set_title(f'WS77: {g.title.strip()}\nQ={g.q} cms, computed profile')
        ax1.legend(loc='upper right', fontsize=9)
        ax1.grid(True, alpha=0.3)

        ax2 = self.canvas.fig.add_subplot(212)
        sigmas = [r['sigma'] for r in res.rows if 0 < r['sigma'] < 100]
        sig_sta = [r['sta'] for r in res.rows if 0 < r['sigma'] < 100]
        if sigmas:
            ax2.plot(sig_sta, sigmas, 'r-', linewidth=2, label='sigma')
            ax2.axhline(0.2, color='k', linestyle=':', alpha=0.5, label='threshold')
        ax2.set_xlabel('Station (m)')
        ax2.set_ylabel('Cavitation index sigma')
        ax2.set_title('Cavitation characteristics')
        ax2.legend(loc='upper right', fontsize=9)
        ax2.grid(True, alpha=0.3)
        self.canvas.fig.tight_layout()
        self.canvas.draw()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = WS77Form()
    w.show()
    sys.exit(app.exec())
