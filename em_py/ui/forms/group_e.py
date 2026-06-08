"""
ui/forms/group_e.py - The 6 sub-tool forms (Group E).

These complement the 8 main tools (Group A-F: WS77, PLOT77, TRAJ, ECAVNO,
CONSTP, DINDX, CONVT, CKDATA) with utility viewers and editors for the raw
data files.

Group E forms:
    E1. StationGridForm      - Sortable/filterable table of all station data
    E2. HydrographForm       - Inflow hydrograph chart editor
    E3. BoundaryLayerForm    - BL velocity-profile chart viewer
    E4. DataCompareForm      - Side-by-side comparison of two data files
    E5. ExporterForm          - Export any data to CSV/JSON
    E6. ReportForm            - Generate a PDF report of a WS77 run

All forms read from APP_STATE (the shared global state) and write back
their results.
"""
from __future__ import annotations
import os
import csv
import json
import math
from PySide6 import QtCore, QtGui, QtWidgets
from ui import mdi_main
from ui.charts.matplotlib_widget import MplCanvas
from em_data import read_geometry_file, read_ws_output, read_bl_file


# =============================================================================
# E1. Station Grid - sortable/filterable table of all station data
# =============================================================================

class StationGridForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E1. Station Grid - Station Data Table")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn_open = QtWidgets.QPushButton("Open GLENIN/SPWY/GLENECN...")
        btn_open.clicked.connect(self._open)
        btn_export = QtWidgets.QPushButton("Export to CSV...")
        btn_export.clicked.connect(self._export_csv)
        h.addWidget(btn_open)
        h.addWidget(btn_export)
        h.addStretch(1)
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by STA value...")
        self.filter_edit.textChanged.connect(self._filter)
        h.addWidget(self.filter_edit)
        layout.addLayout(h)

        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "STA", "Invert", "Width", "SideSlope", "R1",
            "R2", "CL_H", "Wall/C2", "R_Curv", "Rough",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)
        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

    def _open(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open station file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Geometry files (GLENIN GLENECN SPWY)")
        if not path: return
        try:
            g = read_geometry_file(path)
            mdi_main.APP_STATE.geometry = g
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            self._populate(g)
        except Exception as e:
            self.status.setText(f"Error: {e}")

    def _populate(self, g):
        self.table.setRowCount(len(g.stations))
        for i, s in enumerate(g.stations):
            values = [s.sta, s.invert, s.width, s.side_slope, s.r1,
                     s.r2, s.cl_height, s.lower_r, s.rad_curv, s.roughness]
            for j, v in enumerate(values):
                item = QtWidgets.QTableWidgetItem(f"{v:.4f}")
                item.setData(QtCore.Qt.UserRole, v)
                self.table.setItem(i, j, item)
        self.status.setText(f"Loaded {len(g.stations)} stations from {g.title.strip()!r}")

    def _filter(self):
        text = self.filter_edit.text().strip()
        try:
            val = float(text) if text else None
        except ValueError:
            val = None
        for r in range(self.table.rowCount()):
            sta_item = self.table.item(r, 0)
            if sta_item is None:
                continue
            sta = sta_item.data(QtCore.Qt.UserRole)
            show = True
            if val is not None:
                show = abs(sta - val) < 50
            self.table.setRowHidden(r, not show)

    def _export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export to CSV", "stations.csv", "CSV (*.csv)")
        if not path: return
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["STA", "Invert", "Width", "SideSlope", "R1",
                        "R2", "CL_H", "Wall/C2", "R_Curv", "Rough"])
            g = mdi_main.APP_STATE.geometry
            if g is None:
                self.status.setText("No data loaded")
                return
            for s in g.stations:
                w.writerow([s.sta, s.invert, s.width, s.side_slope, s.r1,
                           s.r2, s.cl_height, s.lower_r, s.rad_curv, s.roughness])
        self.status.setText(f"Exported to {path}")


# =============================================================================
# E2. Hydrograph Viewer
# =============================================================================

class HydrographForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E2. Hydrograph - Inflow Discharge vs Time")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        self.q_edit = QtWidgets.QLineEdit("283.168")
        h.addWidget(QtWidgets.QLabel("Q (cms):"))
        h.addWidget(self.q_edit)
        btn_add = QtWidgets.QPushButton("Add row")
        btn_add.clicked.connect(lambda: self._add_row(0, 0))
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(self._clear)
        h.addWidget(btn_add)
        h.addWidget(btn_clear)
        h.addStretch(1)
        layout.addLayout(h)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Time (h)", "Q (cms)"])
        for t, q in [(0, 50), (2, 150), (4, 350), (6, 500), (8, 350),
                     (10, 150), (12, 50)]:
            self._add_row(t, q)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        btn_plot = QtWidgets.QPushButton("Plot")
        btn_plot.clicked.connect(self._plot)
        layout.addWidget(btn_plot)
        self.canvas = MplCanvas(width=8, height=4, dpi=100)
        layout.addWidget(self.canvas)
        self.results = QtWidgets.QLabel("")
        layout.addWidget(self.results)

    def _add_row(self, t, q):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(t)))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(q)))

    def _clear(self):
        self.table.setRowCount(0)

    def _plot(self):
        ts, qs = [], []
        for r in range(self.table.rowCount()):
            try:
                ts.append(float(self.table.item(r, 0).text()))
                qs.append(float(self.table.item(r, 1).text()))
            except (AttributeError, ValueError):
                continue
        if not ts:
            self.results.setText("No data")
            return
        # Compute statistics
        Q_avg = sum(qs) / len(qs) if qs else 0
        Q_peak = max(qs) if qs else 0
        t_peak = ts[qs.index(Q_peak)] if qs else 0
        # Volume by trapezoidal
        vol = sum(0.5 * (qs[i] + qs[i-1]) * (ts[i] - ts[i-1])
                  for i in range(1, len(ts))) if len(ts) > 1 else 0
        vol_mcm = vol * 3600 / 1e6  # convert m^3 to million m^3

        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.fill_between(ts, qs, alpha=0.3, color='blue')
        ax.plot(ts, qs, 'b-', linewidth=2, marker='o', label='Hydrograph')
        ax.axhline(Q_avg, color='g', linestyle='--', label=f'Mean Q = {Q_avg:.1f}')
        ax.plot(t_peak, Q_peak, 'r*', markersize=15, label=f'Peak Q = {Q_peak:.1f} at t={t_peak}')
        ax.set_xlabel('Time (h)')
        ax.set_ylabel('Q (cms)')
        ax.set_title(f'Hydrograph: peak = {Q_peak:.0f} cms, volume = {vol_mcm:.2f} Mm^3')
        ax.legend()
        ax.grid(True, alpha=0.3)
        self.canvas.draw()
        self.results.setText(
            f"Peak Q = {Q_peak:.2f} cms at t = {t_peak:.2f} h; "
            f"Mean Q = {Q_avg:.2f} cms; "
            f"Volume = {vol_mcm:.2f} million m^3")


# =============================================================================
# E3. Boundary Layer Profile Viewer
# =============================================================================

class BoundaryLayerForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E3. Boundary Layer Profile - Velocity Profile Viewer")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn_open = QtWidgets.QPushButton("Open GLENHY/HYDROL...")
        btn_open.clicked.connect(self._open)
        h.addWidget(btn_open)
        h.addStretch(1)
        layout.addLayout(h)

        self.info = QtWidgets.QLabel("No data loaded")
        layout.addWidget(self.info)

        self.canvas = MplCanvas(width=8, height=6, dpi=100)
        layout.addWidget(self.canvas)

    def _open(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open boundary layer file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "BL files (GLENHY HYDROL)")
        if not path: return
        try:
            bl = read_bl_file(path)
            mdi_main.APP_STATE.bl_data = bl
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            self._plot(bl)
        except Exception as e:
            self.info.setText(f"Error: {e}")

    def _plot(self, bl):
        if not bl.profiles:
            self.info.setText("No velocity profiles parsed")
            return
        self.info.setText(
            f"{bl.title.strip()!r}: {bl.n_profiles} profiles, "
            f"{sum(len(p) for p in bl.profiles)} total points"
        )
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        for i, prof in enumerate(bl.profiles[:5]):  # first 5 profiles
            ys = [p.y for p in prof]
            etas = [p.eta for p in prof]
            if ys:
                ax.plot(etas, ys, '-o', markersize=4, label=f'Profile {i+1}')
        # Overlay the 1/7-power-law for comparison
        if bl.profiles and bl.profiles[0]:
            y_max = max(p.y for p in bl.profiles[0])
            n_pts = 30
            eta_th = [i / n_pts for i in range(n_pts + 1)]
            y_th = [y_max * (1 - eta ** (1/7)) for eta in eta_th]
            ax.plot(eta_th, y_th, 'k--', alpha=0.5, label='1/7-power-law')
        ax.set_xlabel('Velocity ratio (u/U)')
        ax.set_ylabel('Distance from wall (m)')
        ax.set_title('Boundary Layer Velocity Profile')
        ax.legend()
        ax.grid(True, alpha=0.3)
        self.canvas.draw()


# =============================================================================
# E4. Data Comparison
# =============================================================================

class DataCompareForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E4. Data Compare - Side-by-side File Comparison")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn1 = QtWidgets.QPushButton("Open File A...")
        btn1.clicked.connect(lambda: self._open('A'))
        btn2 = QtWidgets.QPushButton("Open File B...")
        btn2.clicked.connect(lambda: self._open('B'))
        h.addWidget(btn1); h.addWidget(btn2); h.addStretch(1)
        layout.addLayout(h)

        self.canvas = MplCanvas(width=10, height=6, dpi=100)
        layout.addWidget(self.canvas)

        self.summary = QtWidgets.QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(150)
        layout.addWidget(self.summary)

    def _open(self, slot):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, f"Open file {slot}",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "All data files (*)")
        if not path: return
        try:
            g = read_geometry_file(path)
            if slot == 'A':
                self.gA = g
            else:
                self.gB = g
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            if hasattr(self, 'gA') and hasattr(self, 'gB'):
                self._compare()
        except Exception as e:
            self.summary.setText(f"Error loading {path}: {e}")

    def _compare(self):
        gA, gB = self.gA, self.gB
        lines = [
            f"File A: {gA.title.strip()!r}, Q={gA.q}, NSTA={gA.nsta}",
            f"File B: {gB.title.strip()!r}, Q={gB.q}, NSTA={gB.nsta}",
            f"Q diff: {gA.q - gB.q:+.3f} cms ({(gA.q - gB.q)/gB.q*100 if gB.q else 0:+.1f}%)",
            f"NSTA diff: {gA.nsta - gB.nsta:+d}",
        ]
        self.summary.setPlainText("\n".join(lines))

        # Plot
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        if gA.stations:
            ax.plot([s.sta for s in gA.stations], [s.invert for s in gA.stations],
                    'b-', linewidth=2, label=f'A: {gA.title.strip()[:30]}')
        if gB.stations:
            ax.plot([s.sta for s in gB.stations], [s.invert for s in gB.stations],
                    'r--', linewidth=2, label=f'B: {gB.title.strip()[:30]}')
        ax.set_xlabel('Station (m)')
        ax.set_ylabel('Invert elevation (m)')
        ax.set_title('Profile comparison')
        ax.legend()
        ax.grid(True, alpha=0.3)
        self.canvas.draw()


# =============================================================================
# E5. CSV / JSON Exporter
# =============================================================================

class ExporterForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E5. Exporter - Data Export to CSV / JSON")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn_open = QtWidgets.QPushButton("Open geometry file...")
        btn_open.clicked.connect(self._open)
        h.addWidget(btn_open)
        h.addStretch(1)
        layout.addLayout(h)

        self.status = QtWidgets.QLabel("No data loaded")
        layout.addWidget(self.status)

        h2 = QtWidgets.QHBoxLayout()
        btn_csv = QtWidgets.QPushButton("Export to CSV...")
        btn_csv.clicked.connect(self._export_csv)
        btn_json = QtWidgets.QPushButton("Export to JSON...")
        btn_json.clicked.connect(self._export_json)
        h2.addWidget(btn_csv); h2.addWidget(btn_json); h2.addStretch(1)
        layout.addLayout(h2)

        self.preview = QtWidgets.QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QtGui.QFont("Monospace", 9))
        layout.addWidget(self.preview)

    def _open(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open data file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Geometry files")
        if not path: return
        try:
            g = read_geometry_file(path)
            self.g = g
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            self.status.setText(f"Loaded {g.nsta} stations from {g.title.strip()!r}")
            self._show_preview()
        except Exception as e:
            self.status.setText(f"Error: {e}")

    def _show_preview(self):
        if not hasattr(self, 'g'):
            return
        lines = ["Title:", self.g.title.strip(),
                 f"Q: {self.g.q} cms, y0: {self.g.y0} m, k_s: {self.g.k_s}",
                 f"NSTA: {self.g.nsta}", "", "First 5 stations:"]
        for s in self.g.stations[:5]:
            lines.append(f"  STA={s.sta:.2f}, invert={s.invert:.2f}, "
                          f"width={s.width:.2f}, R1={s.r1:.2f}")
        self.preview.setPlainText("\n".join(lines))

    def _export_csv(self):
        if not hasattr(self, 'g'):
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export to CSV", "data.csv", "CSV (*.csv)")
        if not path: return
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["STA", "Invert", "Width", "SideSlope", "R1",
                        "R2", "CL_H", "Wall_C2", "R_Curv", "Rough"])
            for s in self.g.stations:
                w.writerow([s.sta, s.invert, s.width, s.side_slope, s.r1,
                           s.r2, s.cl_height, s.lower_r, s.rad_curv, s.roughness])
        self.status.setText(f"Exported {len(self.g.stations)} stations to {path}")

    def _export_json(self):
        if not hasattr(self, 'g'):
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export to JSON", "data.json", "JSON (*.json)")
        if not path: return
        data = {
            'title': self.g.title.strip(),
            'q': self.g.q, 'y0': self.g.y0, 'k_s': self.g.k_s,
            'nsta': self.g.nsta, 'n_units': self.g.n_units,
            'stations': [
                {
                    'sta': s.sta, 'invert': s.invert, 'width': s.width,
                    'side_slope': s.side_slope, 'r1': s.r1, 'r2': s.r2,
                    'cl_height': s.cl_height, 'lower_r': s.lower_r,
                    'wall_c2': s.wall_c2, 'rad_curv': s.rad_curv,
                    'roughness': s.roughness,
                } for s in self.g.stations
            ]
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        self.status.setText(f"Exported {len(self.g.stations)} stations to {path}")


# =============================================================================
# E6. Report Generator
# =============================================================================

class ReportForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E6. Report - Generate a Text Report of a WS77 Run")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn_open = QtWidgets.QPushButton("Open GLENOUT / Run WS77...")
        btn_open.clicked.connect(self._open)
        btn_save = QtWidgets.QPushButton("Save report as text...")
        btn_save.clicked.connect(self._save)
        h.addWidget(btn_open); h.addWidget(btn_save); h.addStretch(1)
        layout.addLayout(h)

        self.report = QtWidgets.QTextEdit()
        self.report.setReadOnly(True)
        self.report.setFont(QtGui.QFont("Monospace", 9))
        layout.addWidget(self.report)

    def _open(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open WS77 output",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Output files (GLENOUT)")
        if not path: return
        try:
            o = read_ws_output(path)
            mdi_main.APP_STATE.ws_output = o
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            self._build_report(o)
        except Exception as e:
            self.report.setPlainText(f"Error: {e}")

    def _build_report(self, o):
        lines = []
        lines.append("=" * 70)
        lines.append("WS77 Water Surface Profile Report")
        lines.append("=" * 70)
        lines.append(f"Title:  {o.title}")
        lines.append(f"Q:     {o.q:.3f} cms")
        lines.append(f"y0:    {o.y0:.3f} m")
        lines.append(f"k_s:   {o.roughness_mm:.2f} mm")
        lines.append(f"n:     {o.manning_n:.4f}")
        lines.append(f"EGL_initial: {o.egl_initial:.3f} m")
        lines.append("")
        lines.append("Profile:")
        lines.append("-" * 70)
        lines.append(f"{'STA':>8}  {'Invert':>9}  {'Depth':>7}  {'V':>7}  "
                     f"{'Piez':>7}  {'EGL':>9}  {'Profile':>8}  {'σ':>7}")
        lines.append("-" * 70)
        if o.cavitation_rows:
            cav_by_sta = {r.sta: r for r in o.cavitation_rows}
        else:
            cav_by_sta = {}
        for r in o.profile_rows:
            cav = cav_by_sta.get(r.sta)
            sigma_disp = f"{cav.flow_sigma:.3f}" if cav else "—"
            lines.append(f"{r.sta:>8.2f}  {r.invert:>9.2f}  {r.depth:>7.3f}  "
                         f"{r.velocity:>7.2f}  {r.piez_head:>7.3f}  "
                         f"{r.energy_grade:>9.3f}  {r.profile:>8}  {sigma_disp:>7}")
        lines.append("-" * 70)
        lines.append("")
        lines.append("Cavitation indices (per station):")
        lines.append("-" * 70)
        lines.append(f"{'STA':>8}  {'σ_flow':>7}  {'σ_uniform':>9}  {'Turbulence':>11}")
        for r in o.cavitation_rows:
            lines.append(f"{r.sta:>8.2f}  {r.flow_sigma:>7.3f}  "
                         f"{r.sigma_uniform_roughness:>9.3f}  {r.turbulence:>11.4f}")
        lines.append("=" * 70)
        # Summary
        if o.profile_rows:
            V_max_idx = max(range(len(o.profile_rows)),
                            key=lambda i: o.profile_rows[i].velocity)
            V_max = o.profile_rows[V_max_idx]
            lines.append(f"Max velocity: {V_max.velocity:.2f} m/s at STA {V_max.sta}")
        if o.cavitation_rows:
            sigma_min = min(r.flow_sigma for r in o.cavitation_rows)
            sm_sta = next(r.sta for r in o.cavitation_rows if r.flow_sigma == sigma_min)
            lines.append(f"Min cavitation index: σ = {sigma_min:.3f} at STA {sm_sta}")
        self.report.setPlainText("\n".join(lines))

    def _save(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save report", "ws77_report.txt",
            "Text (*.txt);;Markdown (*.md)")
        if not path: return
        with open(path, 'w') as f:
            f.write(self.report.toPlainText())
