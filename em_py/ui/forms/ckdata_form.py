"""
ui/forms/ckdata_form.py - CKDATA (Check Data) form.
"""
from __future__ import annotations
import os
from PySide6 import QtCore, QtGui, QtWidgets
from ui import mdi_main
from em_ckdata import check_data, format_report
from em_data import read_geometry_file


class CKDATAForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CKDATA - Check Data")
        self._build()
    
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Top: file picker
        h = QtWidgets.QHBoxLayout()
        self.file_edit = QtWidgets.QLineEdit()
        btn_pick = QtWidgets.QPushButton("Browse...")
        btn_pick.clicked.connect(self._pick_file)
        btn_check = QtWidgets.QPushButton("Check")
        btn_check.clicked.connect(self._run_check)
        h.addWidget(QtWidgets.QLabel("Geometry file:"))
        h.addWidget(self.file_edit, 1)
        h.addWidget(btn_pick)
        h.addWidget(btn_check)
        layout.addLayout(h)
        
        # Output: report text + summary label
        self.report = QtWidgets.QTextEdit()
        self.report.setReadOnly(True)
        self.report.setFont(QtGui.QFont("Monospace", 10))
        layout.addWidget(self.report, 1)
        
        self.summary = QtWidgets.QLabel("")
        layout.addWidget(self.summary)
    
    def _pick_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Pick geometry file",
            mdi_main.APP_STATE.last_data_dir or os.path.join(
                os.path.dirname(mdi_main.ROOT), "sample_data", "DATA"),
            "Geometry files (GLENIN SPWY *.INP);;All files (*)")
        if path:
            self.file_edit.setText(path)
            self._run_check()
    
    def _run_check(self):
        path = self.file_edit.text().strip()
        if not path:
            return
        try:
            g = read_geometry_file(path)
            res = check_data(g, filename=os.path.basename(path))
            self.report.setPlainText(format_report(res))
            color = {"0 errors, 0 warnings, ": "green", "0 errors, ": "orange"}.get(
                res.summary()[:11] + " ", "red")
            self.summary.setText(f"  Result: {res.summary()}")
            self.summary.setStyleSheet(f"color: {color}; font-weight: bold;")
        except Exception as e:
            self.report.setPlainText(f"Error reading {path}:\n\n{e}")
            self.summary.setText("")


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = CKDATAForm()
    w.show()
    sys.exit(app.exec())
