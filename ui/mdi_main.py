"""
ui/mdi_main.py - Unified MDI shell for Spillway Workbench.

Combines:
  - Cavicuspill's 19 forms (under "Spillway Design" menu)
  - Cavicuspill v1.4's 6 Group E forms (under "Group E" sub-menu)
  - EM-Py's 8 Falvey tools (under "Cavitation Analysis" menu)
  - EM-Py's 6 utility forms (also under "Group E" sub-menu)
  - Reports (PDF, JSON, CSV) - shared
  - CLI (shared)
  - Bridge: send design to analysis (and vice versa)
"""
from __future__ import annotations
import datetime
import os
import sys
import json
from typing import Optional, List

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

# Make sure imports work from this directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_state import APP_STATE, SpillwayWorkbenchState


# =============================================================================
#  MDI Main Window
# =============================================================================
class SpillwayWorkbenchMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spillway Workbench v1.0 (Cavicuspill + EM-Py)")
        self.resize(1500, 950)

        # MDI area
        self.mdi = QtWidgets.QMdiArea()
        self.mdi.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.mdi.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.mdi.setViewMode(QtWidgets.QMdiArea.SubWindowView)
        self.setCentralWidget(self.mdi)

        # Build menus
        self._build_file_menu()
        self._build_design_menu()       # Cavicuspill (19 forms)
        self._build_analysis_menu()     # EM-Py (8 forms)
        self._build_group_e_menu()      # 6 Cavicuspill + 6 EM-Py utility forms
        self._build_bridge_menu()       # Cross-bridge
        self._build_reports_menu()      # PDF/JSON/CSV/CLI
        self._build_help_menu()

        # Status bar
        self.statusBar().showMessage(
            f"Ready -- Spillway Workbench v1.0 -- {datetime.date.today().isoformat()}"
        )

    # ------------------------------------------------------------------ File
    def _build_file_menu(self):
        m = self.menuBar().addMenu("&File")
        m.addAction("&New Workspace", self.on_new, "Ctrl+N")
        m.addAction("&Open Geometry...", self.on_open, "Ctrl+O")
        m.addSeparator()
        m.addAction("&Save Workspace...", self.on_save, "Ctrl+S")
        m.addAction("&Save State to JSON...", self.on_save_state)
        m.addSeparator()
        m.addAction("E&xit", self.close, "Ctrl+Q")

    def on_new(self):
        APP_STATE.cav = APP_STATE.get_cav_state()  # reset
        APP_STATE.em_geometry = None
        APP_STATE.em_ws_output = None
        APP_STATE.bridge_invert_profile = []
        for sub in list(self.mdi.subWindowList()):
            sub.close()
        self.statusBar().showMessage("Workspace reset.")

    def on_open(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Spillway / Geometry file", APP_STATE.last_dir,
            "Geometry files (*.dat *.in *.txt);;All files (*)")
        if path:
            self.load_geometry_file(path)

    def load_geometry_file(self, path: str):
        """Try to auto-detect the file format (Cavicuspill vs EM-Py) and load."""
        APP_STATE.last_dir = os.path.dirname(path)
        base = os.path.basename(path).upper()
        em_paths = ["GLENIN", "SPWY", "HYDROL", "GLENECN", "GLENTD", "GLENSD", "GLENHY"]
        if base in em_paths or any(base.startswith(p) for p in em_paths):
            self._load_em_geometry(path)
        else:
            # Try Cavicuspill first
            try:
                self._load_cav_geometry(path)
                self.statusBar().showMessage(f"Loaded Cavicuspill geometry: {path}")
            except Exception as e:
                # Fall back to EM-Py
                try:
                    self._load_em_geometry(path)
                    self.statusBar().showMessage(f"Loaded EM-Py geometry: {path}")
                except Exception as e2:
                    QtWidgets.QMessageBox.critical(
                        self, "Load failed",
                        f"Could not load {path} as Cavicuspill or EM-Py.\n\n"
                        f"Cavicuspill error: {e}\nEM-Py error: {e2}")

    def _load_cav_geometry(self, path: str):
        # A Cavicuspill geometry file would be loaded via the Reservoir
        # Properties form. Here we just open that form with the file path.
        self.open_cav_form("reservoir_properties", "Reservoir Properties")
        self.statusBar().showMessage(f"Opened Cavicuspill Reservoir form for {path}")

    def _load_em_geometry(self, path: str):
        from em_py.em_data import read_geometry_file
        APP_STATE.em_geometry = read_geometry_file(path)
        self.statusBar().showMessage(
            f"EM-Py geometry loaded: {os.path.basename(path)} -- "
            f"{len(APP_STATE.em_geometry.stations)} stations, "
            f"Q={APP_STATE.em_geometry.q:.2f} m^3/s")

    def on_save(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Workspace", APP_STATE.last_dir,
            "Cavicuspill workspace (*.cav.json);;All files (*)")
        if path:
            self.on_save_state(path=path)

    def on_save_state(self, path: str = None):
        if not path:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save State", APP_STATE.last_dir,
                "JSON (*.json);;All files (*)")
        if not path:
            return
        payload = {
            "version": "1.0",
            "cav_reservoir_loaded": APP_STATE.get_cav_state().reservoir,
            "cav_spillway_loaded": APP_STATE.get_cav_state().spillwayData,
            "cav_inflow_loaded": APP_STATE.get_cav_state().inFlow,
            "bridge_invert_profile": APP_STATE.bridge_invert_profile,
            "bridge_cross_section": APP_STATE.bridge_cross_section,
            "bridge_design_summary": APP_STATE.bridge_design_summary,
        }
        if APP_STATE.em_geometry is not None:
            g = APP_STATE.em_geometry
            payload["em_geometry"] = {
                "title": g.title, "q": g.q, "y0": g.y0, "k_s": g.k_s,
                "nsta": g.nsta, "slope_initial": g.slope_initial,
                "stations": [
                    {"sta": s.sta, "invert": s.invert, "width": s.width,
                     "r1": s.r1, "r2": s.r2, "cl_height": s.cl_height,
                     "geom_code1": s.geom_code1, "rad_curv": s.rad_curv}
                    for s in g.stations
                ],
            }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        self.statusBar().showMessage(f"State saved to {path}")

    # ------------------------------------------------------ Spillway Design
    def _build_design_menu(self):
        """Cavicuspill's 19 forms, organised into subgroups A-E."""
        cav = self.menuBar().addMenu("&Spillway Design")
        # Sub-group A: Flood Routing
        sg_a = cav.addMenu("&A. Flood Routing")
        sg_a.addAction("1. Reservoir Properties...",
                       lambda: self.open_cav_form("reservoir_properties", "Reservoir Properties"))
        sg_a.addAction("2. Spillway Data...",
                       lambda: self.open_cav_form("spillway_data", "Spillway Data"))
        sg_a.addAction("3. Inflow Data...",
                       lambda: self.open_cav_form("inflow_data", "Inflow Data"))
        sg_a.addAction("4. Calculate Outflow...",
                       lambda: self.open_cav_form("outflow", "Calculate Outflow"))
        # Sub-group B: Spillway Properties
        sg_b = cav.addMenu("&B. Spillway Properties")
        sg_b.addAction("5. Spillway Profile...",
                       lambda: self.open_cav_form("spillway_profile", "Spillway Profile"))
        sg_b.addAction("6. Spillway Properties...",
                       lambda: self.open_cav_form("spillway_properties", "Spillway Properties"))
        # Sub-group C: Cross-Sections
        sg_c = cav.addMenu("&C. Cross-Sections")
        for cs in ["rectangular", "trangular", "tropizodal", "egg",
                    "circular", "horse_shoe", "modified_horse_shoe",
                    "rectangular_corner", "trangular_corner"]:
            label = cs.replace("_", " ").title()
            sg_c.addAction(label,
                           lambda c=cs, l=label: self.open_cav_form(c, l))
        # Sub-group D: Calculations
        sg_d = cav.addMenu("&D. Calculations")
        sg_d.addAction("Surface Profile...",
                       lambda: self.open_cav_form("surface_profile", "Surface Profile"))
        sg_d.addAction("Cavitation Number...",
                       lambda: self.open_cav_form("cavitation_no", "Cavitation Number"))
        sg_d.addAction("Cavitation Damage...",
                       lambda: self.open_cav_form("cavitation_damage", "Cavitation Damage"))
        sg_d.addAction("Air Entrainment...",
                       lambda: self.open_cav_form("air_entrainment", "Air Entrainment"))
        cav.addSeparator()
        cav.addAction("&Open all 19 forms",
                       lambda: self._open_all_cav_forms())

    def open_cav_form(self, key: str, title: str):
        """Open a Cavicuspill form.  Reuses the existing ui.forms.* modules."""
        # Check if already open
        for sub in self.mdi.subWindowList():
            if sub.windowTitle() == title:
                self.mdi.setActiveSubWindow(sub)
                return
        try:
            from cavicuspill.ui.forms import (
                reservoir_properties, spillway_data, inflow_data, outflow,
                spillway_profile, spillway_properties, cross_section,
                surface_profile, cavitation_no, cavitation_damage,
                air_entrainment,
            )
            form_map = {
                "reservoir_properties": (reservoir_properties, "ReservoirPropertiesForm"),
                "spillway_data": (spillway_data, "SpillwayDataForm"),
                "inflow_data": (inflow_data, "InflowDataForm"),
                "outflow": (outflow, "OutflowForm"),
                "spillway_profile": (spillway_profile, "SpillwayProfileForm"),
                "spillway_properties": (spillway_properties, "SpillwayPropertiesForm"),
                "surface_profile": (surface_profile, "SurfaceProfileForm"),
                "cavitation_no": (cavitation_no, "CavitationNoForm"),
                "cavitation_damage": (cavitation_damage, "CavitationDamageForm"),
                "air_entrainment": (air_entrainment, "AirEntrainmentForm"),
            }
            for cs_name in ["rectangular", "trangular", "tropizodal", "egg",
                            "circular", "horse_shoe", "modified_horse_shoe",
                            "rectangular_corner", "trangular_corner"]:
                form_map[cs_name] = (cross_section, f"CrossSectionForm_{cs_name}")
            if key not in form_map:
                self._open_placeholder(title, f"Form '{key}' not in map.")
                return
            mod, cls_name = form_map[key]
            cls = getattr(mod, cls_name, None) or getattr(mod, "Form", None)
            if cls is None:
                # Try the first QMdiSubWindow in the module
                for name in dir(mod):
                    obj = getattr(mod, name)
                    if isinstance(obj, type) and issubclass(obj, QtWidgets.QMdiSubWindow):
                        cls = obj
                        break
            if cls is None:
                self._open_placeholder(title, f"No QMdiSubWindow class in {mod.__name__}")
                return
            sub = cls(self.mdi)
            sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            sub.setWindowTitle(title)
            self.mdi.addSubWindow(sub)
            sub.show()
        except Exception as e:
            self._open_placeholder(title, f"Error opening form: {e}")

    def _open_placeholder(self, title: str, message: str = ""):
        sub = QtWidgets.QMdiSubWindow(self.mdi)
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(QtWidgets.QLabel(f"<b>{title}</b>"))
        if message:
            v.addWidget(QtWidgets.QLabel(message))
        v.addStretch(1)
        sub.setWidget(w)
        sub.setWindowTitle(title)
        sub.resize(400, 200)
        sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.mdi.addSubWindow(sub)
        sub.show()

    def _open_all_cav_forms(self):
        for key, title in [
            ("reservoir_properties", "Reservoir Properties"),
            ("spillway_data", "Spillway Data"),
            ("inflow_data", "Inflow Data"),
            ("outflow", "Calculate Outflow"),
            ("spillway_profile", "Spillway Profile"),
            ("spillway_properties", "Spillway Properties"),
            ("surface_profile", "Surface Profile"),
            ("cavitation_no", "Cavitation Number"),
            ("cavitation_damage", "Cavitation Damage"),
            ("air_entrainment", "Air Entrainment"),
        ]:
            self.open_cav_form(key, title)
        for cs in ["rectangular", "trangular", "tropizodal", "egg",
                    "circular", "horse_shoe", "modified_horse_shoe",
                    "rectangular_corner", "trangular_corner"]:
            self.open_cav_form(cs, cs.replace("_", " ").title())

    # --------------------------------------------------- Cavitation Analysis
    def _build_analysis_menu(self):
        """EM-Py's 8 Falvey tools (matching MENUHD.BAT F1-F8)."""
        em = self.menuBar().addMenu("&Cavitation Analysis")
        em.addAction("&1. Water Surface Profile (WS77)...",
                     lambda: self.open_em_form("ws77", "WS77 - Water Surface Profile"))
        em.addAction("&2. Plot Results (PLOT77)...",
                     lambda: self.open_em_form("plot77", "PLOT77 - Plot Results"))
        em.addAction("&3. Aerator Trajectory (TRAJ)...",
                     lambda: self.open_em_form("traj", "TRAJ - Aerator Trajectory"))
        em.addAction("&4. Equal Cavitation Number (ECAVNO)...",
                     lambda: self.open_em_form("ecavno", "ECAVNO - Equal Cavitation Number"))
        em.addAction("&5. Controlled Pressure (CONSTP)...",
                     lambda: self.open_em_form("constp", "CONSTP - Controlled Pressure"))
        em.addAction("&6. Damage Index (DINDX)...",
                     lambda: self.open_em_form("dindx", "DINDX - Damage Index"))
        em.addAction("&7. Convert Units (CONVT)...",
                     lambda: self.open_em_form("convt", "CONVT - Convert Units"))
        em.addAction("&8. Check Data (CKDATA)...",
                     lambda: self.open_em_form("ckdata", "CKDATA - Check Data"))
        em.addSeparator()
        em.addAction("Load &Glen Canyon sample...",
                     lambda: self._load_em_sample("glen_canyon"))
        em.addAction("Load &Blue Mesa sample...",
                     lambda: self._load_em_sample("blue_mesa"))
        em.addAction("Load &Hoover Dam sample...",
                     lambda: self._load_em_sample("hoover"))

    def open_em_form(self, key: str, title: str):
        # Check if already open
        for sub in self.mdi.subWindowList():
            if sub.windowTitle() == title:
                self.mdi.setActiveSubWindow(sub)
                return
        try:
            from em_py.ui.forms import (
                ws77_form, plot77_form, traj_form, ecavno_form, constp_form,
                dindx_form, convt_form, ckdata_form, about_form,
            )
            form_map = {
                "ws77": (ws77_form, "Ws77Form"),
                "plot77": (plot77_form, "Plot77Form"),
                "traj": (traj_form, "TrajForm"),
                "ecavno": (ecavno_form, "EcavnoForm"),
                "constp": (constp_form, "ConstpForm"),
                "dindx": (dindx_form, "DindxForm"),
                "convt": (convt_form, "ConvtForm"),
                "ckdata": (ckdata_form, "CkdataForm"),
            }
            if key not in form_map:
                self._open_placeholder(title, f"EM-Py form '{key}' not in map.")
                return
            mod, cls_name = form_map[key]
            cls = getattr(mod, cls_name, None)
            if cls is None:
                for name in dir(mod):
                    obj = getattr(mod, name)
                    if isinstance(obj, type) and issubclass(obj, QtWidgets.QMdiSubWindow):
                        cls = obj
                        break
            if cls is None:
                self._open_placeholder(title, f"No QMdiSubWindow class in {mod.__name__}")
                return
            sub = cls(self.mdi)
            sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            sub.setWindowTitle(title)
            self.mdi.addSubWindow(sub)
            sub.show()
        except Exception as e:
            self._open_placeholder(title, f"Error: {e}")

    def _load_em_sample(self, name: str):
        from em_py.em_data import load_sample_data
        data = load_sample_data(name)
        if isinstance(data, dict):
            APP_STATE.em_geometry = data.get('geometry')
            APP_STATE.em_ws_output = data.get('ws_output')
        else:
            APP_STATE.em_geometry = data
        if APP_STATE.em_geometry is not None:
            self.statusBar().showMessage(
                f"Sample loaded: {name} -- "
                f"{len(APP_STATE.em_geometry.stations)} stations, "
                f"Q={APP_STATE.em_geometry.q:.2f} m^3/s")

    # ------------------------------------------------------------ Group E
    def _build_group_e_menu(self):
        """The 6 Cavicuspill + 6 EM-Py utility forms."""
        ge = self.menuBar().addMenu("&Group E")
        cav_sub = ge.addMenu("&Cavicuspill sub-grids")
        for key, (title, _) in [
            ("e1", ("E1. Reservoir Properties Grid", None)),
            ("e2", ("E2. Inflow Data Grid", None)),
            ("e3", ("E3. Outflow Data Grid", None)),
            ("e4", ("E4. Spillway Data Grid", None)),
            ("e5", ("E5. Profile Data", None)),
            ("e6", ("E6. Outflow Diagram", None)),
        ]:
            cav_sub.addAction(title,
                              lambda k=key, t=title: self._open_cav_group_e(k, t))
        em_sub = ge.addMenu("&EM-Py utilities")
        for key, (title, _) in [
            ("e1", ("EM1. Station Grid", None)),
            ("e2", ("EM2. Hydrograph Viewer", None)),
            ("e3", ("EM3. Boundary Layer Profile", None)),
            ("e4", ("EM4. Data Compare", None)),
            ("e5", ("EM5. Exporter", None)),
            ("e6", ("EM6. Report Generator", None)),
        ]:
            em_sub.addAction(title,
                             lambda k=key, t=title: self._open_em_group_e(k, t))

    def _open_cav_group_e(self, key: str, title: str):
        for sub in self.mdi.subWindowList():
            if sub.windowTitle() == title:
                self.mdi.setActiveSubWindow(sub)
                return
        try:
            from cavicuspill.ui.forms.group_e import GROUP_E_FORMS
            form_class = GROUP_E_FORMS[key][1]
            sub = form_class(self.mdi)
            sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.mdi.addSubWindow(sub)
            sub.show()
        except Exception as e:
            self._open_placeholder(title, f"Error: {e}")

    def _open_em_group_e(self, key: str, title: str):
        for sub in self.mdi.subWindowList():
            if sub.windowTitle() == title:
                self.mdi.setActiveSubWindow(sub)
                return
        try:
            from em_py.ui.forms.group_e import GROUP_E_FORMS
            form_class = GROUP_E_FORMS[key][1]
            sub = form_class(self.mdi)
            sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.mdi.addSubWindow(sub)
            sub.show()
        except Exception as e:
            self._open_placeholder(title, f"Error: {e}")

    # ----------------------------------------------------------- Bridge
    def _build_bridge_menu(self):
        b = self.menuBar().addMenu("&Bridge")
        b.addAction("Send Cavicuspill design to EM-Py...",
                    self.bridge_cav_to_em)
        b.addAction("Send EM-Py geometry to Cavicuspill...",
                    self.bridge_em_to_cav)
        b.addSeparator()
        # Cross-bridge hooks (richer domain-specific translations)
        hk = b.addMenu("&Cross-bridge hooks")
        hk.addAction("Cavicuspill damage -> EM-Py chamfer recs...",
                     self.hook_cav_damage_to_chamfer)
        hk.addAction("EM-Py geometry -> WES spillway design...",
                     self.hook_em_to_wes)
        hk.addAction("Find optimal aerator station...",
                     self.hook_find_aerator)
        b.addSeparator()
        b.addAction("Show &APP_STATE summary...",
                    self.show_state_summary)

    def bridge_cav_to_em(self):
        ok = APP_STATE.bridge_from_cav_to_em()
        if ok:
            QtWidgets.QMessageBox.information(
                self, "Bridge: Cavicuspill -> EM-Py",
                f"EM-Py geometry built from Cavicuspill design:\n"
                f"  {len(APP_STATE.em_geometry.stations)} stations\n"
                f"  Q = {APP_STATE.em_geometry.q:.2f} m^3/s\n"
                f"  y0 = {APP_STATE.em_geometry.y0:.2f} m\n\n"
                f"You can now open 'Cavitation Analysis > WS77' to compute the "
                f"water surface profile.")
        else:
            QtWidgets.QMessageBox.warning(
                self, "Bridge failed",
                "Cavicuspill design data is not complete. Please run:\n"
                "  - Spillway Design > A. Flood Routing (1-4)\n"
                "  - Spillway Design > B. Spillway Properties (5-6)\n"
                "Then try bridging again.")

    def bridge_em_to_cav(self):
        ok = APP_STATE.bridge_from_em_to_cav()
        if ok:
            QtWidgets.QMessageBox.information(
                self, "Bridge: EM-Py -> Cavicuspill",
                f"Cavicuspill design summary built from EM-Py geometry:\n"
                f"  {len(APP_STATE.bridge_invert_profile)} invert points\n"
                f"  Lc = {APP_STATE.bridge_cross_section.get('Lc', 30):.1f} m\n"
                f"  Q = {APP_STATE.bridge_cross_section.get('Q', 0):.1f} m^3/s")
        else:
            QtWidgets.QMessageBox.warning(
                self, "Bridge failed",
                "No EM-Py geometry loaded. Use 'Cavitation Analysis > "
                "Load sample...' or 'File > Open Geometry...' first.")

    def show_state_summary(self):
        QtWidgets.QMessageBox.information(self, "APP_STATE", APP_STATE.summary())

    # ----------------------------------------------------------- Cross-bridge hooks
    def hook_cav_damage_to_chamfer(self):
        """Take Cavicuspill damage results, recommend EM-Py chamfer ratios."""
        from swb.bridge_hooks import cav_damage_to_chamfer_recommendations
        cav_state = APP_STATE.get_cav_state()
        if cav_state.cavitation_damage is None:
            QtWidgets.QMessageBox.warning(
                self, "No Cavicuspill damage",
                "Run Cavicuspill's Cavitation Damage form first, then try again.")
            return
        if APP_STATE.em_geometry is None:
            QtWidgets.QMessageBox.warning(
                self, "No EM-Py geometry",
                "Load an EM-Py geometry (Cavitation Analysis > Load sample).")
            return
        recs = cav_damage_to_chamfer_recommendations(cav_state, APP_STATE.em_geometry)
        if not recs:
            QtWidgets.QMessageBox.information(self, "No recommendations", "No chamfer recommendations available.")
            return
        # Open a small dialog showing the recommendations
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Chamfer Recommendations (from Cavicuspill damage)")
        dlg.resize(800, 400)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(
            f"<b>Chamfer recommendations for {len(recs)} stations</b><br>"
            "<i>Lower ratios = gentler chamfer = less expensive; "
            "higher ratios = steeper chamfer = better damage reduction.</i>"))
        table = QtWidgets.QTableWidget(len(recs), 8)
        table.setHorizontalHeaderLabels([
            "STA", "V (m/s)", "sigma", "No chamfer",
            "1:4", "1:2", "1:1", "Recommended"])
        for i, r in enumerate(recs):
            table.setItem(i, 0, QtWidgets.QTableWidgetItem(f"{r.sta:.1f}"))
            table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{r.velocity:.2f}"))
            table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{r.sigma:.3f}"))
            table.setItem(i, 3, QtWidgets.QTableWidgetItem(f"{r.damage_no_chamfer:.2f}"))
            table.setItem(i, 4, QtWidgets.QTableWidgetItem(f"{r.chamfer_1_4:.2f}"))
            table.setItem(i, 5, QtWidgets.QTableWidgetItem(f"{r.chamfer_1_2:.2f}"))
            table.setItem(i, 6, QtWidgets.QTableWidgetItem(f"{r.chamfer_1_1:.2f}"))
            table.setItem(i, 7, QtWidgets.QTableWidgetItem(r.recommended_ratio))
        table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(table)
        btn_h = QtWidgets.QHBoxLayout()
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(dlg.close)
        btn_h.addWidget(btn_close)
        v.addLayout(btn_h)
        dlg.exec()

    def hook_em_to_wes(self):
        """Take EM-Py geometry, run WES design to extract P, H, L."""
        from swb.bridge_hooks import em_geometry_to_cav_wes
        if APP_STATE.em_geometry is None:
            QtWidgets.QMessageBox.warning(
                self, "No geometry", "Load an EM-Py geometry first.")
            return
        wes = em_geometry_to_cav_wes(APP_STATE.em_geometry)
        if not wes:
            QtWidgets.QMessageBox.information(self, "No WES result", "WES design failed.")
            return
        text = "<b>WES Spillway Design (reverse-engineered from EM-Py geometry)</b><br><br>"
        text += "<table border='1' cellpadding='6'>"
        for k, v in wes.items():
            text += f"<tr><td>{k}</td><td>{v:.4g}</td></tr>"
        text += "</table>"
        QtWidgets.QMessageBox.information(self, "WES Design", text)

    def hook_find_aerator(self):
        """Locate the optimal aerator station in the EM-Py geometry."""
        from swb.bridge_hooks import find_aerator_station
        if APP_STATE.em_geometry is None:
            QtWidgets.QMessageBox.warning(
                self, "No geometry", "Load an EM-Py geometry first.")
            return
        sta, V, sigma = find_aerator_station(APP_STATE.em_geometry)
        QtWidgets.QMessageBox.information(
            self, "Optimal Aerator Location",
            f"<b>Recommended aerator station</b><br><br>"
            f"Station: {sta:.1f} m<br>"
            f"Approach V: {V:.2f} m/s<br>"
            f"sigma at this station: {sigma:.3f}<br><br>"
            f"<i>Place the aerator just upstream of this station. "
            f"Higher V and lower sigma = higher cavitation risk = "
            f"aerator is most needed here.</i>")

    # --------------------------------------------------------- Reports
    def _build_reports_menu(self):
        r = self.menuBar().addMenu("&Reports")
        r.addAction("Generate &PDF Report...", self.generate_pdf_report)
        r.addAction("Export to &JSON...", self.export_json)
        r.addAction("Export to &CSV...", self.export_csv)
        r.addSeparator()
        r.addAction("&Open CLI Terminal...", self.show_cli_help)

    def generate_pdf_report(self):
        if APP_STATE.em_geometry is None:
            QtWidgets.QMessageBox.warning(
                self, "No geometry",
                "Load an EM-Py geometry first (Cavitation Analysis > Load sample).")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF Report", "swb_report.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            from em_py.em_ws77 import compute_profile
            from em_py.em_report import make_pdf_report
            res = compute_profile(APP_STATE.em_geometry)
            APP_STATE.em_ws_output = res
            make_pdf_report(APP_STATE.em_geometry, res, path)
            QtWidgets.QMessageBox.information(
                self, "PDF generated", f"Saved to:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "PDF failed", str(e))

    def export_json(self):
        if APP_STATE.em_geometry is None:
            QtWidgets.QMessageBox.warning(self, "No geometry",
                "Load an EM-Py geometry first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save JSON", "swb_results.json", "JSON (*.json)")
        if not path:
            return
        from em_py.em_ws77 import compute_profile
        res = compute_profile(APP_STATE.em_geometry)
        with open(path, "w") as f:
            json.dump({"egl_initial": res.egl_initial, "rows": res.rows},
                       f, indent=2, default=float)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved to:\n{path}")

    def export_csv(self):
        if APP_STATE.em_geometry is None:
            QtWidgets.QMessageBox.warning(self, "No geometry",
                "Load an EM-Py geometry first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV", "swb_results.csv", "CSV (*.csv)")
        if not path:
            return
        from em_py.em_ws77 import compute_profile
        import csv
        res = compute_profile(APP_STATE.em_geometry)
        if not res.rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=res.rows[0].keys())
            w.writeheader()
            w.writerows(res.rows)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved to:\n{path}")

    def show_cli_help(self):
        help_text = """Spillway Workbench Command-Line Interface

From a terminal, you can run any tool directly:

  # WS77 water surface profile
  python -m em_py.em_cli ws77 --input sample_data/DATA/GLENIN --output report.pdf

  # Convert units
  python -m em_py.em_cli convt --value 283.168 --from cms --to cfs

  # Validate a geometry
  python -m em_py.em_cli ckdata --input sample_data/DATA/GLENIN

  # Aerator jet trajectory
  python -m em_py.em_cli traj --input sample_data/DATA/GLENIN --sta 720

  # Controlled pressure
  python -m em_py.em_cli constp --input sample_data/DATA/GLENIN --kind sinusoidal

  # Equal cavitation number design
  python -m em_py.em_cli ecavno --input sample_data/DATA/GLENIN --sigma 0.2

  # Damage index
  python -m em_py.em_cli dindx --input hydrograph.txt

Run `python -m em_py.em_cli --help` for full options.
"""
        QtWidgets.QMessageBox.information(self, "CLI Help", help_text)

    # --------------------------------------------------------- Help
    def _build_help_menu(self):
        m = self.menuBar().addMenu("&Help")
        m.addAction("&About Spillway Workbench...", self.on_about)
        m.addAction("&Version", self.on_version)

    def on_about(self):
        text = """<h2>Spillway Workbench v1.0</h2>
<p>A unified Python 3 / PySide6 workbench combining:</p>
<ul>
<li><b>Cavicuspill v1.4</b> -- spillway design (flood routing, WES design,
cavitation damage, air entrainment). Ported from Abbas A. Hebah's VB6
original (2004-2006).</li>
<li><b>EM-Py v0.4</b> -- cavitation analysis (water surface profile,
boundary layer, cavitation index, damage rates). Ported from USBR Henry T.
Falvey's "Cavitation Programs" (1987/1990).</li>
</ul>
<p>The two share an MDI shell, an APP_STATE, a Reports menu, a CLI, and a
single PyInstaller binary.</p>
<p><b>Form count:</b> 19 Cavicuspill + 6 Cavicuspill Group E + 8 EM-Py
Falvey + 6 EM-Py utility = <b>39 forms</b>.</p>
<p><b>Algorithms:</b> 25 ported from published physics (Falvey 1990
Monograph No. 42, USBR Design of Small Dams 1987).</p>
<p>MIT License.</p>
"""
        QtWidgets.QMessageBox.about(self, "About Spillway Workbench", text)

    def on_version(self):
        QtWidgets.QMessageBox.information(
            self, "Version", "Spillway Workbench v1.0\nCavicuspill v1.4 + EM-Py v0.4")


# =============================================================================
#  Entry point
# =============================================================================
def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = SpillwayWorkbenchMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
