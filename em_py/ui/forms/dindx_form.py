"""
ui/forms/dindx_form.py - DINDX (Damage Index) form.
"""
from __future__ import annotations
from PySide6 import QtCore, QtWidgets
from ui.charts.matplotlib_widget import MplCanvas
from em_dindx import (SigmaQData, HydrographPoint, fit_sigma_q,
                      sigma_at_q, total_damage,
                      DEFAULT_DAMAGE_COEFFS, DEFAULT_90_DEG_COEFFS)


class DINDXForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DINDX - Damage Index")
        self._build()
    
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # === Left: input panels ===
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        
        # (Q, sigma) calibration data
        gb_cal = QtWidgets.QGroupBox("Sigma vs. Q calibration data")
        gbl = QtWidgets.QVBoxLayout(gb_cal)
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Q (cms)", "sigma"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        for q, s in [(100, 0.42), (200, 0.30), (500, 0.20), (1000, 0.15)]:
            self._append_row(q, s)
        gbl.addWidget(self.table)
        h = QtWidgets.QHBoxLayout()
        b1 = QtWidgets.QPushButton("Add row"); b1.clicked.connect(lambda: self._append_row(0, 0))
        b2 = QtWidgets.QPushButton("Remove last"); b2.clicked.connect(self._remove_row)
        h.addWidget(b1); h.addWidget(b2); h.addStretch(1)
        gbl.addLayout(h)
        lv.addWidget(gb_cal)
        
        # Damage curve choice
        gb_dc = QtWidgets.QGroupBox("Damage curve")
        gdl = QtWidgets.QFormLayout(gb_dc)
        self.dc_type = QtWidgets.QComboBox()
        self.dc_type.addItems(list(DEFAULT_DAMAGE_COEFFS.keys()))
        self.dc_90 = QtWidgets.QCheckBox("Use 90-degree offset coefficients")
        gdl.addRow("Offset:", self.dc_type)
        gdl.addRow("", self.dc_90)
        lv.addWidget(gb_dc)
        
        # Hydrograph
        gb_h = QtWidgets.QGroupBox("Hydrograph (Q vs. time)")
        ghl = QtWidgets.QVBoxLayout(gb_h)
        self.ht = QtWidgets.QTableWidget(0, 2)
        self.ht.setHorizontalHeaderLabels(["t (h)", "Q (cms)"])
        self.ht.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        for t, q in [(0,50), (2, 100), (4, 300), (6, 500), (8, 300), (10, 100), (12, 50)]:
            self._append_h(t, q)
        ghl.addWidget(self.ht)
        h2 = QtWidgets.QHBoxLayout()
        b3 = QtWidgets.QPushButton("Add row"); b3.clicked.connect(lambda: self._append_h(0, 0))
        b4 = QtWidgets.QPushButton("Remove last"); b4.clicked.connect(self._remove_h)
        h2.addWidget(b3); h2.addWidget(b4); h2.addStretch(1)
        ghl.addLayout(h2)
        lv.addWidget(gb_h)
        
        btn_calc = QtWidgets.QPushButton("Compute cumulative damage")
        btn_calc.clicked.connect(self._compute)
        lv.addWidget(btn_calc)
        self.result_label = QtWidgets.QLabel("Result: (click Compute)")
        self.result_label.setStyleSheet("font-weight: bold;")
        lv.addWidget(self.result_label)
        lv.addStretch(1)
        
        # === Right: matplotlib chart ===
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.canvas = MplCanvas(width=6, height=5, dpi=100)
        rv.addWidget(self.canvas)
        btn_export = QtWidgets.QPushButton("Export chart as PNG...")
        btn_export.clicked.connect(self._export_png)
        rv.addWidget(btn_export)
        
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
    
    def _append_row(self, q, s):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(q)))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(s)))
    
    def _remove_row(self):
        if self.table.rowCount() > 0:
            self.table.removeRow(self.table.rowCount() - 1)
    
    def _append_h(self, t, q):
        r = self.ht.rowCount()
        self.ht.insertRow(r)
        self.ht.setItem(r, 0, QtWidgets.QTableWidgetItem(str(t)))
        self.ht.setItem(r, 1, QtWidgets.QTableWidgetItem(str(q)))
    
    def _remove_h(self):
        if self.ht.rowCount() > 0:
            self.ht.removeRow(self.ht.rowCount() - 1)
    
    def _read_table(self, table):
        out = []
        for r in range(table.rowCount()):
            try:
                x = float(table.item(r, 0).text())
                y = float(table.item(r, 1).text())
                out.append((x, y))
            except (AttributeError, ValueError):
                continue
        return out
    
    def _compute(self):
        try:
            pts = [SigmaQData(q=q, sigma=s) for q, s in self._read_table(self.table)]
            if len(pts) < 2:
                self.result_label.setText("Need at least 2 calibration points.")
                return
            fit = fit_sigma_q(pts)
            hydro = [HydrographPoint(t=t, q=q) for t, q in self._read_table(self.ht)]
            if not hydro:
                self.result_label.setText("Need at least 1 hydrograph point.")
                return
            use_90 = self.dc_90.isChecked()
            if use_90:
                res = total_damage(hydro, fit, self.dc_type.currentText(), use_90=True)
            else:
                res = total_damage(hydro, fit, self.dc_type.currentText())
            self.result_label.setText(
                f"Result: total damage = {res.total_damage:.4e} in, "
                f"sigma range = [{res.sigma_min:.3f}, {res.sigma_max:.3f}]")
            self._plot(pts, fit, hydro, res, use_90)
        except Exception as e:
            self.result_label.setText(f"Error: {e}")
    
    def _plot(self, pts, fit, hydro, res, use_90):
        self.canvas.fig.clear()
        # 2 subplots: sigma vs Q (calibration + fit), damage vs time
        ax1 = self.canvas.fig.add_subplot(211)
        qs = [p.q for p in pts]; ss = [p.sigma for p in pts]
        ax1.scatter(qs, ss, color='red', s=80, zorder=3, label='Data')
        qfit = [min(qs)*0.5, max(qs)*2.0]
        sfit = [sigma_at_q(q, fit) for q in qfit]
        ax1.plot(qfit, sfit, 'b-', label=f'Fit: log10(sigma)={fit.a:.3f}+{fit.b:.3f}*log10(Q)')
        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel('Discharge Q (cms)')
        ax1.set_ylabel('Cavitation index sigma')
        ax1.set_title('Calibration: sigma vs Q')
        ax1.grid(True, which='both', alpha=0.3)
        ax1.legend(fontsize=9)
        
        ax2 = self.canvas.fig.add_subplot(212)
        ts = [t for t, _, _ in res.damage_trace]
        ds = [d for _, _, d in res.damage_trace]
        ax2.fill_between(ts, ds, alpha=0.3, color='orange')
        ax2.plot(ts, ds, 'r-', linewidth=2)
        ax2.set_xlabel('Time (hours)')
        ax2.set_ylabel(f'Damage rate (in/hr) [{"90-deg" if use_90 else "circ-arc"}, {res.damage_curve}]')
        ax2.set_title(f'Cumulative damage = {res.total_damage:.3e} in')
        ax2.grid(True, alpha=0.3)
        self.canvas.draw()
    
    def _export_png(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save chart", "dindx_chart.png", "PNG (*.png)")
        if path:
            self.canvas.fig.savefig(path, dpi=150)
            QtWidgets.QMessageBox.information(self, "Saved", f"Wrote {path}")


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = DINDXForm()
    w.show()
    sys.exit(app.exec())
