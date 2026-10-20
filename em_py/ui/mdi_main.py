"""
ui/mdi_main.py - MDI main window for the EM-Py (Falvey Cavitation Programs) app.

The 8 top-level menus mirror the original MENUHD.BAT (DOS):
    F1 - WS77     (Water Surface Profile)
    F2 - PLOT77   (Plot Results)
    F3 - TRAJ     (Aerator Trajectory)
    F4 - ECAVNO   (Equal Cavitation Number)
    F5 - CONSTP   (Controlled Pressure)
    F6 - DINDX    (Damage Index)
    F7 - CONVT    (Convert Units)
    F8 - CKDATA   (Check Data)

The MDI shell uses an MdiArea so each tool opens in its own sub-window.
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

# Project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@dataclass
class EmAppState:
    """Global state shared between MDI sub-windows.
    
    Mirrors the original Cavicuspill's APP_STATE pattern.
    """
    # Geometry input (loaded from GLENIN/SPWY)
    geometry: object = None      # GeometryFile
    # Computed water surface profile (output from WS77)
    ws_output: object = None     # WSOutput
    # ECAVNO problem definition
    ecn_input: object = None     # ECNInput
    # Plot-ready data (output from PLOT77)
    plot_data: object = None
    # Boundary layer measurements
    bl_data: object = None
    # Last data file path
    last_data_dir: str = ""





APP_STATE = EmAppState()


class MdiMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EM-Py - Cavitation Programs (Port of Falvey 1987/1990)")
        self.resize(1280, 800)
        self._build_ui()
        self._build_menus()
        self._build_statusbar()
    
    def _build_ui(self):
        # MDI area
        self.mdi = QtWidgets.QMdiArea()
        self.mdi.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.mdi.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.mdi.setViewMode(QtWidgets.QMdiArea.SubWindowView)
        self.setCentralWidget(self.mdi)
        
        # Icon (if available)
        for icon_name in ("cavicuspill.png", "em.png", "logo.png"):
            ip = os.path.join(ROOT, icon_name)
            if os.path.exists(ip):
                self.setWindowIcon(QtGui.QIcon(ip))
                break
    
    def _build_menus(self):
        mb = self.menuBar()
        
        # === File menu ===
        file_menu = mb.addMenu("&File")
        file_menu.addAction("&Open Geometry File...", self.open_geometry_file, "Ctrl+O")
        file_menu.addAction("Open &WS Output File...", self.open_ws_output_file)
        file_menu.addAction("Open &ECN Input Files...", self.open_ecn_input)
        file_menu.addSeparator()
        file_menu.addAction("&Save Workspace...", self.save_workspace)
        file_menu.addAction("&Load Workspace...", self.load_workspace)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close, "Ctrl+Q")
        
        # === Tools menu (the 8 Falvey tools) ===
        tools_menu = mb.addMenu("&Tools")
        # F1: WS77
        tools_menu.addAction("&1. Water Surface Profile (WS77)...",
                             lambda: self.open_subwindow("ws77", "WS77 - Water Surface Profile"))
        # F2: PLOT77
        tools_menu.addAction("&2. Plot Results (PLOT77)...",
                             lambda: self.open_subwindow("plot77", "PLOT77 - Plot Results"))
        # F3: TRAJ
        tools_menu.addAction("&3. Aerator Trajectory (TRAJ)...",
                             lambda: self.open_subwindow("traj", "TRAJ - Aerator Trajectory"))
        # F4: ECAVNO
        tools_menu.addAction("&4. Equal Cavitation Number (ECAVNO)...",
                             lambda: self.open_subwindow("ecavno", "ECAVNO - Equal Cavitation Number"))
        # F5: CONSTP
        tools_menu.addAction("&5. Controlled Pressure (CONSTP)...",
                             lambda: self.open_subwindow("constp", "CONSTP - Controlled Pressure Spillway"))
        # F6: DINDX
        tools_menu.addAction("&6. Damage Index (DINDX)...",
                             lambda: self.open_subwindow("dindx", "DINDX - Damage Index"))
        # F7: CONVT
        tools_menu.addAction("&7. Convert Units (CONVT)...",
                             lambda: self.open_subwindow("convt", "CONVT - Convert Units"))
        # F8: CKDATA
        tools_menu.addAction("&8. Check Data (CKDATA)...",
                             lambda: self.open_subwindow("ckdata", "CKDATA - Check Data"))
        
        # === Sample data menu ===
        # === Reports menu (v0.4) ===
        reports_menu = mb.addMenu("&Reports")
        reports_menu.addAction("&Generate PDF Report...",
                                self.generate_pdf_report)
        reports_menu.addAction("&Export to JSON...",
                                self.export_json)
        reports_menu.addAction("&Export to CSV...",
                                self.export_csv)
        reports_menu.addSeparator()
        reports_menu.addAction("&Open CLI Terminal...",
                                self.show_cli_help)

        sample_menu = mb.addMenu("&Sample Data")
        sample_menu.addAction("Load &Glen Canyon sample...",
                             lambda: self.load_sample("glen_canyon"))
        sample_menu.addAction("Load &Blue Mesa sample...",
                             lambda: self.load_sample("blue_mesa"))
        sample_menu.addAction("Load &Hoover sample...",
                             lambda: self.load_sample("hoover"))
        
        # === Window menu ===
        win_menu = mb.addMenu("&Window")
        win_menu.addAction("&Cascade", self.mdi.cascadeSubWindows)
        win_menu.addAction("&Tile", self.mdi.tileSubWindows)
        win_menu.addAction("&Close All", self.mdi.closeAllSubWindows)
        
        # === Group E menu (utility forms) ===
        e_menu = mb.addMenu("&Utilities (Group E)")
        e_menu.addAction("E1. Station Grid...",
                         lambda: self.open_subwindow("e1", "E1. Station Grid"))
        e_menu.addAction("E2. Hydrograph Viewer...",
                         lambda: self.open_subwindow("e2", "E2. Hydrograph Viewer"))
        e_menu.addAction("E3. Boundary Layer Profile...",
                         lambda: self.open_subwindow("e3", "E3. Boundary Layer Profile"))
        e_menu.addAction("E4. Data Compare...",
                         lambda: self.open_subwindow("e4", "E4. Data Compare"))
        e_menu.addAction("E5. Exporter (CSV/JSON)...",
                         lambda: self.open_subwindow("e5", "E5. Exporter"))
        e_menu.addAction("E6. Report Generator...",
                         lambda: self.open_subwindow("e6", "E6. Report Generator"))

        # === Help menu ===
        help_menu = mb.addMenu("&Help")
        help_menu.addAction("&About EM-Py...", self.show_about)
        help_menu.addAction("&Documentation", self.show_docs)
        # === v0.4 Report export methods ===
    def generate_pdf_report(self):
        from em_report import make_pdf_report
        from PySide6 import QtWidgets
        from em_data import read_geometry_file
        from em_ws77 import compute_profile
        if not APP_STATE.geometry:
            QtWidgets.QMessageBox.warning(self, "No data",
                "Please load a sample first (Sample Data menu).")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF Report", "ws77_report.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            res = compute_profile(APP_STATE.geometry)
            make_pdf_report(APP_STATE.geometry, res, path)
            QtWidgets.QMessageBox.information(self, "PDF generated",
                f"PDF report saved to:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "PDF failed", str(e))

    def export_json(self):
        from PySide6 import QtWidgets
        import json
        from em_ws77 import compute_profile
        if not APP_STATE.geometry:
            QtWidgets.QMessageBox.warning(self, "No data",
                "Please load a sample first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save JSON", "ws77_results.json", "JSON (*.json)")
        if not path:
            return
        res = compute_profile(APP_STATE.geometry)
        with open(path, "w") as f:
            json.dump({"egl_initial": res.egl_initial, "rows": res.rows},
                       f, indent=2, default=float)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved to:\n{path}")

    def export_csv(self):
        from PySide6 import QtWidgets
        import csv
        from em_ws77 import compute_profile
        if not APP_STATE.geometry:
            QtWidgets.QMessageBox.warning(self, "No data",
                "Please load a sample first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV", "ws77_results.csv", "CSV (*.csv)")
        if not path:
            return
        res = compute_profile(APP_STATE.geometry)
        if not res.rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=res.rows[0].keys())
            w.writeheader()
            w.writerows(res.rows)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved to:\n{path}")

    def show_cli_help(self):
        from PySide6 import QtWidgets
        help_text = """EM-Py Command-Line Interface

From a terminal, run em_py scripts directly:

  python em_cli.py ws77 --input GLENIN --output report.pdf
  python em_cli.py ws77 --input GLENIN --output results.json
  python em_cli.py convt --value 283.168 --from cms --to cfs
  python em_cli.py ckdata --input GLENIN
  python em_cli.py traj --input GLENIN --sta 720
  python em_cli.py constp --input GLENIN --kind sinusoidal
  python em_cli.py ecavno --input GLENIN --sigma 0.2

Run `python em_cli.py --help` for full options.
"""
        QtWidgets.QMessageBox.information(self, "CLI Help", help_text)


    def _build_statusbar(self):
        self.sb = self.statusBar()
        self.sb.showMessage("Ready. Load sample data from the Sample Data menu.")
    
    # ------------------------------------------------------------------
    # Sub-window management
    # ------------------------------------------------------------------
    
    def open_subwindow(self, tool_id: str, title: str):
        """Open (or focus) the sub-window for the given tool."""
        # Already open?
        for sub in self.mdi.subWindowList():
            wid = sub.widget()
            if wid.property("tool_id") == tool_id:
                self.mdi.setActiveSubWindow(sub)
                return
        # Import the form class and instantiate
        try:
            from ui.forms import ws77_form, plot77_form, traj_form, ecavno_form
            from ui.forms import constp_form, dindx_form, convt_form, ckdata_form
            from ui.forms import group_e
            form_map = {
                "ws77": ws77_form.WS77Form,
                "plot77": plot77_form.PLOT77Form,
                "traj": traj_form.TRAJForm,
                "ecavno": ecavno_form.ECAVNOForm,
                "constp": constp_form.CONSTPForm,
                "dindx": dindx_form.DINDXForm,
                "convt": convt_form.CONVTForm,
                "ckdata": ckdata_form.CKDATAForm,
                "e1": group_e.StationGridForm,
                "e2": group_e.HydrographForm,
                "e3": group_e.BoundaryLayerForm,
                "e4": group_e.DataCompareForm,
                "e5": group_e.ExporterForm,
                "e6": group_e.ReportForm,
            }
            cls = form_map.get(tool_id)
            if cls is None:
                QtWidgets.QMessageBox.warning(self, "Unknown tool", f"Tool: {tool_id}")
                return
            widget = cls()
            widget.setProperty("tool_id", tool_id)
            sub = self.mdi.addSubWindow(widget)
            sub.setWindowTitle(title)
            sub.resize(900, 650)
            sub.show()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, "Open tool failed",
                                           f"Could not open {title}:\n\n{e}")
    
    # ------------------------------------------------------------------
    # File I/O actions
    # ------------------------------------------------------------------
    
    def open_geometry_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Geometry File",
            APP_STATE.last_data_dir or os.path.join(ROOT, "sample_data", "DATA"),
            "Geometry files (GLENIN SPWY *.INP);;All files (*)")
        if not path:
            return
        try:
            from em_data import read_geometry_file
            APP_STATE.geometry = read_geometry_file(path)
            APP_STATE.last_data_dir = os.path.dirname(path)
            self.sb.showMessage(f"Loaded {os.path.basename(path)}: "
                                f"Q={APP_STATE.geometry.q}, NSTA={APP_STATE.geometry.nsta}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(e))
    
    def open_ws_output_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open WS77 Output File",
            APP_STATE.last_data_dir or os.path.join(ROOT, "sample_data", "DATA"),
            "Output files (GLENOUT *.OUT);;All files (*)")
        if not path:
            return
        try:
            from em_data import read_ws_output
            APP_STATE.ws_output = read_ws_output(path)
            APP_STATE.last_data_dir = os.path.dirname(path)
            self.sb.showMessage(
                f"Loaded {os.path.basename(path)}: "
                f"{len(APP_STATE.ws_output.profile_rows)} profile rows, "
                f"{len(APP_STATE.ws_output.cavitation_rows)} cavitation rows")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(e))
    
    def open_ecn_input(self):
        dat_dir = APP_STATE.last_data_dir or os.path.join(ROOT, "sample_data", "DATA")
        ecn_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open ECNDAT (problem definition)", dat_dir,
            "ECNDAT")
        if not ecn_path:
            return
        glenecn_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open GLENECN (station geometry)", dat_dir,
            "GLENECN")
        if not glenecn_path:
            return
        try:
            from em_data import read_ecn_input
            APP_STATE.ecn_input = read_ecn_input(ecn_path, glenecn_path)
            self.sb.showMessage(
                f"Loaded ECN input: Q={APP_STATE.ecn_input.q}, "
                f"sigma_target={APP_STATE.ecn_input.sigma_target}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(e))
    
    def load_sample(self, name: str):
        from em_data import load_sample_data
        try:
            data = load_sample_data(name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load sample failed", str(e))
            return
        APP_STATE.geometry = data.get("geometry")
        APP_STATE.ws_output = data.get("ws_output")
        APP_STATE.ecn_input = data.get("ecndat")
        APP_STATE.plot_data = data.get("plot")
        APP_STATE.bl_data = data.get("boundary_layer")
        n = sum(1 for v in (APP_STATE.geometry, APP_STATE.ws_output,
                            APP_STATE.ecn_input, APP_STATE.plot_data,
                            APP_STATE.bl_data) if v is not None)
        self.sb.showMessage(
            f"Loaded {name} sample: {n} files. Open any tool to view data.")
    
    def save_workspace(self):
        QtWidgets.QMessageBox.information(self, "Save workspace",
            "Workspace save/load is a stub in this version. "
            "Use the individual file open/save buttons in each tool.")
    
    def load_workspace(self):
        pass
    
    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    
    def show_about(self):
        from ui.forms.about_form import AboutForm
        dlg = AboutForm(self)
        dlg.exec()
    
    def show_docs(self):
        QtWidgets.QMessageBox.information(self, "Documentation",
            "EM-Py v0.1 - A modern Python port of the Bureau of Reclamation\n"
            "'Cavitation Programs' toolset (Falvey, June 1987; revised 1990).\n\n"
            "See README.md in the project root for full documentation.\n"
            "The 8 original tools (WS77, PLOT77, TRAJ, ECAVNO, CONSTP, DINDX,\n"
            "CONVT, CKDATA) are all accessible from the Tools menu.")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("EM-Py")
    app.setOrganizationName("U.S. Bureau of Reclamation (port)")
    win = MdiMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
