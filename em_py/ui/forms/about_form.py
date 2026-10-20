"""
ui/forms/about_form.py - About dialog.
"""
from __future__ import annotations
from PySide6 import QtCore, QtGui, QtWidgets


ABOUT_TEXT = """
<h2>EM-Py v0.1</h2>
<p><b>A modern Python port of the U.S. Bureau of Reclamation<br>
"Cavitation Programs" toolset</b></p>
<p>Original DOS Fortran 77: Henry T. Falvey, USBR (June 1987, revised April 1990).<br>
Modernization: 2026, PySide6 / NumPy / Matplotlib.</p>
<p>The 8 original tools are available from the <b>Tools</b> menu:</p>
<ol>
  <li><b>WS77</b> — Water Surface Profile (energy balance, boundary layer, cavitation)</li>
  <li><b>PLOT77</b> — Plot Results (matplotlib replacement for PLOT88 line-printer graphics)</li>
  <li><b>TRAJ</b> — Aerator Jet Trajectory and Air Flow Rates</li>
  <li><b>ECAVNO</b> — Equal Cavitation Number Spillway (iterative design)</li>
  <li><b>CONSTP</b> — Controlled Pressure Spillway (sinusoidal / triangular)</li>
  <li><b>DINDX</b> — Damage Index (cumulative cavitation damage vs. discharge)</li>
  <li><b>CONVT</b> — Convert Units (SI &harr; English)</li>
  <li><b>CKDATA</b> — Check Data (geometry file validator)</li>
</ol>
<p>Reference: Henry T. Falvey, "Cavitation in Chutes and Spillways",<br>
USBR Engineering Monograph No. 42, 1990.</p>
<p>Bundled sample data:<br>
&nbsp;&nbsp;Glen Canyon Dam Left Spillway Tunnel (27 stations, 283 m^3/s)<br>
&nbsp;&nbsp;Blue Mesa Dam Spillway (25 stations, 28.3 m^3/s)<br>
&nbsp;&nbsp;Hoover Dam Boundary Layer Measurements</p>
<p>License: MIT</p>
""".strip()


class AboutForm(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About EM-Py")
        self.resize(560, 540)
        layout = QtWidgets.QVBoxLayout(self)
        text = QtWidgets.QTextBrowser()
        text.setHtml(ABOUT_TEXT)
        text.setOpenExternalLinks(True)
        layout.addWidget(text)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
