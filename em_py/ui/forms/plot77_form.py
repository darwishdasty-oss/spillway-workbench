"""
ui/forms/plot77_form.py - PLOT77 (Plot Results) form.

The original PLOT77.EXE used the PLOT88 library to produce line-printer
graphics. This Python port renders publication-quality matplotlib charts
from a parsed GLENPLOT or GLENOUT file.
"""
from __future__ import annotations
import os
from PySide6 import QtCore, QtGui, QtWidgets
from ui.charts.matplotlib_widget import MplCanvas
from ui import mdi_main
from em_data import read_ws_output, read_plot_file, WSOutput, ProfileRow, CavitationRow


def _ws77_result_to_output(res):
    """Convert em_ws77.WS77Result to em_data.WSOutput for plotting."""
    o = WSOutput(
        title='Computed profile',
        q=res.rows[0].get('Q', 0) if res.rows else 0,
        y0=0, roughness_mm=0, manning_n=0,
        egl_initial=res.egl_initial,
    )
    for r in res.rows:
        o.profile_rows.append(ProfileRow(
            sta=r['sta'], invert=r['invert'], slope=r['slope'],
            depth=r['depth'], velocity=r['velocity'],
            piez_head=r['piez_head'], energy_grade=r['egl'],
            q_air_over_q_water=r.get('q_air', 0),
            profile=r['profile'],
            normal_depth=r['y_normal'],
            critical_depth=r['y_critical'],
            boundary_layer=r['boundary_layer'],
        ))
    return o


class PLOT77Form(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PLOT77 - Plot Results")
        self._build()
    
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        btn_open_out = QtWidgets.QPushButton("Open GLENOUT (computed)...")
        btn_open_out.clicked.connect(self._open_out)
        btn_open_plot = QtWidgets.QPushButton("Open GLENPLOT (plot input)...")
        btn_open_plot.clicked.connect(self._open_plot)
        btn_export = QtWidgets.QPushButton("Export PNG...")
        btn_export.clicked.connect(self._export)
        h.addWidget(btn_open_out)
        h.addWidget(btn_open_plot)
        h.addStretch(1)
        h.addWidget(btn_export)
        layout.addLayout(h)
        
        # Layout: 1x2 of subplots: profile, cavitation
        self.canvas = MplCanvas(width=10, height=8, dpi=100)
        layout.addWidget(self.canvas)
        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)
    
    def _open_out(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open WS77 output",
            mdi_main.APP_STATE.last_data_dir or "",
            "WS77 output (GLENOUT *.OUT);;All files (*)")
        if not path: return
        try:
            o = read_ws_output(path)
            mdi_main.APP_STATE.ws_output = o
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            self._plot_from_output(o)
        except Exception as e:
            self.status.setText(f"Error: {e}")
    
    def _open_plot(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open PLOT77 input",
            mdi_main.APP_STATE.last_data_dir or "",
            "Plot files (GLENPLOT);;All files (*)")
        if not path: return
        try:
            p = read_plot_file(path)
            mdi_main.APP_STATE.plot_data = p
            mdi_main.APP_STATE.last_data_dir = os.path.dirname(path)
            self.status.setText(f"Loaded plot file: {p.n_sta} stations, {p.n_plots} plots")
        except Exception as e:
            self.status.setText(f"Error: {e}")
    
    def _plot_from_output(self, o):
        self.canvas.fig.clear()
        # Subplot 1: profile (invert + water surface)
        ax1 = self.canvas.fig.add_subplot(211)
        if o.profile_rows:
            sta = [r.sta for r in o.profile_rows]
            inv = [r.invert for r in o.profile_rows]
            wse = [r.invert + r.depth for r in o.profile_rows]
            ax1.plot(sta, inv, 'k-', linewidth=2, label='Invert')
            ax1.plot(sta, wse, 'b-', linewidth=1.5, label='Water surface')
            egl = [r.energy_grade for r in o.profile_rows]
            ax1.plot(sta, egl, 'r--', linewidth=1, label='Energy grade line', alpha=0.7)
            ax1.fill_between(sta, inv, wse, color='cyan', alpha=0.2)
            ax1.set_ylabel('Elevation (m)')
            ax1.set_title(f"Water Surface Profile — Q={o.q} cms, n={o.manning_n}, k_s={o.roughness_mm} mm")
            ax1.legend(loc='upper right', fontsize=9)
            ax1.grid(True, alpha=0.3)
        # Subplot 2: cavitation index
        ax2 = self.canvas.fig.add_subplot(212)
        if o.cavitation_rows:
            sta = [r.sta for r in o.cavitation_rows]
            sigma = [r.flow_sigma for r in o.cavitation_rows]
            ax2.plot(sta, sigma, 'r-', linewidth=2, label='sigma (flow)')
            sigma_r = [r.sigma_uniform_roughness for r in o.cavitation_rows]
            ax2.plot(sta, sigma_r, 'b--', linewidth=1, label='sigma_r (uniform roughness)', alpha=0.7)
            ax2.axhline(0.2, color='k', linestyle=':', alpha=0.5, label='cavitation threshold')
            ax2.set_xlabel('Station (m)')
            ax2.set_ylabel('Cavitation index')
            ax2.set_title('Cavitation Characteristics')
            ax2.legend(loc='upper right', fontsize=9)
            ax2.grid(True, alpha=0.3)
        self.canvas.fig.tight_layout()
        self.canvas.draw()
        self.status.setText(
            f"Plotted {len(o.profile_rows)} profile + "
            f"{len(o.cavitation_rows)} cavitation rows")
    
    def _export(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export chart", "plot77.png", "PNG (*.png);;PDF (*.pdf)")
        if path:
            self.canvas.fig.savefig(path, dpi=150)
            self.status.setText(f"Wrote {path}")


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = PLOT77Form()
    w.show()
    sys.exit(app.exec())
