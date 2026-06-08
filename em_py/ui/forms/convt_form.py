"""
ui/forms/convt_form.py - CONVT (Unit Conversion) form.
"""
from __future__ import annotations
import os, sys
from PySide6 import QtCore, QtGui, QtWidgets
from ui import mdi_main
from em_convert import (ft_to_m, m_to_ft, cfs_to_cms, cms_to_cfs,
                        in_to_mm, mm_to_in, f_to_c, c_to_f,
                        psi_to_pa, pa_to_psi, lbf_to_n, n_to_lbf)


class CONVTForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CONVT - Unit Conversion")
        self._build()
    
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # === Group 1: Geometry file conversion ===
        gb_file = QtWidgets.QGroupBox("Geometry File Conversion (SI <-> English)")
        fl = QtWidgets.QFormLayout(gb_file)
        self.file_in = QtWidgets.QLineEdit()
        self.file_out = QtWidgets.QLineEdit()
        btn_pick = QtWidgets.QPushButton("...")
        btn_pick.setFixedWidth(40)
        btn_pick.clicked.connect(self._pick_input_file)
        h = QtWidgets.QHBoxLayout()
        h.addWidget(self.file_in)
        h.addWidget(btn_pick)
        w_in = QtWidgets.QWidget(); w_in.setLayout(h)
        fl.addRow("Input geometry file:", w_in)
        fl.addRow("Output file:", self.file_out)
        btn_convert = QtWidgets.QPushButton("Convert and Save")
        btn_convert.clicked.connect(self._convert_file)
        fl.addRow(btn_convert)
        layout.addWidget(gb_file)
        
        # === Group 2: Single-value conversions ===
        gb_val = QtWidgets.QGroupBox("Single-Value Conversions")
        gl = QtWidgets.QFormLayout(gb_val)
        self.val_in = QtWidgets.QDoubleSpinBox()
        self.val_in.setRange(-1e15, 1e15)
        self.val_in.setDecimals(6)
        self.val_in.setValue(1.0)
        self.val_unit = QtWidgets.QComboBox()
        self.val_unit.addItems([
            "Feet -> Meters", "Meters -> Feet",
            "CFS -> CMS", "CMS -> CFS",
            "Inches -> Millimeters", "Millimeters -> Inches",
            "Fahrenheit -> Celsius", "Celsius -> Fahrenheit",
            "PSI -> Pa", "Pa -> PSI",
            "lbf -> Newton", "Newton -> lbf",
        ])
        self.val_out = QtWidgets.QLineEdit()
        self.val_out.setReadOnly(True)
        self.val_in.valueChanged.connect(self._update_conversion)
        self.val_unit.currentIndexChanged.connect(self._update_conversion)
        gl.addRow("Input value:", self.val_in)
        gl.addRow("Conversion:", self.val_unit)
        gl.addRow("Result:", self.val_out)
        layout.addWidget(gb_val)
        
        layout.addStretch(1)
        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)
        
        self._update_conversion()
    
    def _pick_input_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Pick geometry file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Geometry files (GLENIN SPWY *.INP);;All files (*)")
        if path:
            self.file_in.setText(path)
            if not self.file_out.text():
                base, ext = os.path.splitext(path)
                new_units = "_SI" if "_ENG" in path.upper() else "_ENG"
                self.file_out.setText(f"{base}{new_units}{ext or '.INP'}")
    
    def _convert_file(self):
        from em_data import read_geometry_file
        from em_convert import convert_geometry_file
        in_path = self.file_in.text().strip()
        out_path = self.file_out.text().strip()
        if not in_path or not out_path:
            self.status.setText("Set both input and output file paths first.")
            return
        try:
            g = read_geometry_file(in_path)
            g2 = convert_geometry_file(g)
            g2.write(out_path)
            self.status.setText(f"Wrote {out_path}  ({g2.nsta} stations, "
                                f"{'SI' if g2.is_si else 'English'})")
        except Exception as e:
            self.status.setText(f"Error: {e}")
    
    def _update_conversion(self):
        v = self.val_in.value()
        idx = self.val_unit.currentIndex()
        convs = [
            (ft_to_m, "m"),  (m_to_ft, "ft"),
            (cfs_to_cms, "cms"), (cms_to_cfs, "cfs"),
            (in_to_mm, "mm"), (mm_to_in, "in"),
            (f_to_c, "C"), (c_to_f, "F"),
            (psi_to_pa, "Pa"), (pa_to_psi, "psi"),
            (lbf_to_n, "N"), (n_to_lbf, "lbf"),
        ]
        fn, unit = convs[idx]
        self.val_out.setText(f"{fn(v):.6g} {unit}")


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = CONVTForm()
    w.show()
    sys.exit(app.exec())
