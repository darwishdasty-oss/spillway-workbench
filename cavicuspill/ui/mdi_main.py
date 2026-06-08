"""
Cavicuspill-Qt — the modern Python 3 / PySide6 port of the original
2005 Visual Basic 6.0 Cavicuspill workbench.

This is the MDI shell (Phase 1 of 8). It reproduces the seven
top-level menus and the submenu structure of the original Cavicuspill
main window (CavicuspillFrm), wired up to placeholder dialogs.

Phase roadmap (collaborative; we work through them together):
  Phase 0  [done]  - cavicuspill.py: 1:1 algorithm port (12 functions)
  Phase 1  [now]   - MDI shell with 7 top-level menus + 9 cross-sections
  Phase 2  - Reservoir Properties dialog (data entry)
  Phase 3  - Spillway Data + Spillway Properties dialogs
  Phase 4  - Inflow + Outflow dialogs (Pulse-Method routing)
  Phase 5  - Profile Data + Surface Profile + Spillway Profile (WES)
  Phase 6  - Cavitation No + Air Entrainment + Cavitation Damage
  Phase 7  - All 9 cross-section geometry dialogs
  Phase 8  - Save/load .cav project files, polish, package

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations

import os
import sys
import json
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

# Re-use the algorithm port
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cavicuspill as cav  # noqa: E402


# =============================================================================
#  APPLICATION STATE  (mirrors the AppState pattern of globals.bas)
# =============================================================================
@dataclass
class AppState:
    """Mirrors the `appState` global from globals.bas. Each Boolean flag
    is set to True when the corresponding data-entry form is closed
    with OK, and is required for the next downstream form to be enabled.
    """
    # 1. data-entry states
    reservoir:        bool = False
    spillwayData:     bool = False
    inFlow:           bool = False
    outflow:          bool = False
    spillwayProperties: bool = False
    profileData:      bool = False
    spillwayProfile:  bool = False
    surfaceProfile:   bool = False
    cavitationNo:     bool = False
    cavitationDamage: bool = False
    airEntrainment:   bool = False
    # 2. cross-sections
    crossSections:    str  = ""  # "" = none, else "Rectangular"/"Trapezoidal"/etc.
    # 3. the input data itself (populated by the data-entry forms)
    reservoir_data:   Optional[cav.ReservoirTable] = None
    spillway_cfg:     Optional[cav.SpillwayConfig] = None
    inflow:           Optional[cav.InflowHydrograph] = None
    wes_design:       Optional[dict] = None
    surface_profile:  Optional[dict] = None
    cavitation_result: Optional[dict] = None
    air_entrainment_result: Optional[dict] = None
    cavitation_damage: Optional[dict] = None
    cross_section_result: Optional[dict] = None


APP_STATE = AppState()


# =============================================================================
#  PLACEHOLDER DIALOG
#    Used by the MDI shell to open a "this dialog is not yet ported"
#    window when a menu item is clicked. Each placeholder is replaced
#    by a real dialog in its respective phase.
# =============================================================================
class PlaceholderDialog(QtWidgets.QMdiSubWindow):
    """A generic placeholder for a not-yet-ported VB6 form."""

    PHASE_INFO = {
        "ReservoirProperties":     ("Reservoir Properties",       "Phase 2",
            "Elevation-storage-discharge table for the reservoir."),
        "SpillWayData":            ("Spillway Data",              "Phase 3",
            "Spillway length range, increment, discharge coefficient, routing Δt."),
        "SpillWayProperties":      ("Spillway Properties",        "Phase 3",
            "Storage-discharge (G-Q) curves for candidate spillway lengths."),
        "InFlowData":              ("Inflow Data",                "Phase 4",
            "Inflow unit hydrograph data-entry grid."),
        "Outflow":                 ("Outflow",                    "Phase 4",
            "Pulse-Method flood-routing result; outflow hydrograph."),
        "ProfileData":             ("Profile Data",               "Phase 5",
            "Surface profile cross-section station coordinates."),
        "SurfaceProfile":          ("Surface Profile",            "Phase 5",
            "Standard-Step water-surface profile computation."),
        "SpillWayProfile":         ("Spillway Profile (WES)",     "Phase 5",
            "WES standard overflow-spillway design for the four slopes."),
        "CavitationNo":            ("Cavitation No.",             "Phase 6",
            "Flow-surface / singular-roughness / uniform-roughness cavitation index."),
        "AirEntrainment":          ("Air Entrainment",            "Phase 6",
            "Downstream air-entrainment analysis for aerator design."),
        "CavitationDamage":        ("Cavitation Damage",          "Phase 6",
            "Cavitation-damage rate along the spillway face."),
    }

    def __init__(self, form_key: str, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        title, phase, desc = self.PHASE_INFO[form_key]
        self.setWindowTitle(title)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(520, 340)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        h = QtWidgets.QHBoxLayout()
        icon = QtWidgets.QLabel("\u26A0")   # warning sign
        f = icon.font(); f.setPointSize(28); icon.setFont(f)
        icon.setStyleSheet("color: #B8730A;")
        h.addWidget(icon, 0, QtCore.Qt.AlignTop)

        text = QtWidgets.QLabel()
        text.setTextFormat(QtCore.Qt.RichText)
        text.setText(
            f"<h2 style='color:#1A3A6C; margin:0'>{title}</h2>"
            f"<p style='color:#666; font-style:italic; margin:4px 0'>"
            f"Status: <b>{phase}</b> &mdash; not yet ported in this build</p>"
            f"<p>{desc}</p>"
            f"<p style='color:#444'>This dialog corresponds to the original "
            f"Visual Basic 6.0 form <code>{form_key}.frm</code> in the "
            f"<code>Cavicuspill.vbp</code> project. The underlying algorithm "
            f"is already ported in <code>cavicuspill.py</code>; only the "
            f"dialog widgets and data-binding remain.</p>"
        )
        text.setWordWrap(True)
        h.addWidget(text, 1)
        v.addLayout(h)

        v.addStretch(1)

        # OK / Cancel buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        ok = QtWidgets.QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.close)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        v.addLayout(btn_row)


# =============================================================================
#  MDI MAIN WINDOW
#    Replicates the seven top-level menus of the original CavicuspillFrm
# =============================================================================
class CavicuspillMainWindow(QtWidgets.QMainWindow):
    """The main MDI shell, replicating CavicuspillFrm.frm."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cavicuspill — Python 3 / PySide6 port of the 2005 VB6 workbench")
        self.resize(1100, 720)

        # ---------- Central MDI area ----------
        self.mdi = QtWidgets.QMdiArea()
        self.mdi.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.mdi.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.mdi.setViewMode(QtWidgets.QMdiArea.SubWindowView)
        self.mdi.setDocumentMode(True)
        self.mdi.setBackground(QtGui.QBrush(QtGui.QColor("#dcdad5")))
        self.setCentralWidget(self.mdi)

        # ---------- Menus ----------
        self._build_file_menu()
        self._build_flood_routing_menu()
        self._build_spillway_menu()
        self._build_cross_sections_menu()
        self._build_calculations_menu()
        self._build_show_diagrams_menu()
        self._build_help_menu()
        self._build_admin_menus()
        self._build_group_e_menu()

        # ---------- Toolbar (icon row above the MDI area) ----------
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QtCore.QSize(20, 20))
        for label, slot in [
            ("New",      self.on_new),
            ("Open...",  self.on_open),
            ("Save",     self.on_save),
            ("Save as...", self.on_save_as),
            ("|",        None),
            ("Run all",  self.on_run_all),
            ("Charts",   self.on_show_charts),
            ("|",        None),
            ("About",    self.on_about),
        ]:
            if label == "|":
                tb.addSeparator()
            else:
                act = QtGui.QAction(label, self)
                if slot is not None:
                    act.triggered.connect(slot)
                tb.addAction(act)
        self.toolbar = tb

        # ---------- Status bar ----------
        self.statusBar().showMessage(
            f"Ready  \u2014  Cavicuspill-Py v0.1 (MDI shell, Phase 1 of 8)  "
            f"\u2014  {datetime.date.today().isoformat()}"
        )

        # Initialise menu-enable state (mimics the original's appState logic)
        self._refresh_menu_state()

        # Refresh menu state whenever any sub-window closes (since closing
        # a data-entry form is when its state flag gets set)
        self.mdi.subWindowActivated.connect(self._on_subwindow_activated)

    # ------------------------------------------------------------------
    #  MENU BUILDERS
    # ------------------------------------------------------------------
    def _build_file_menu(self):
        m = self.menuBar().addMenu("&File")
        for label, slot, shortcut in [
            ("&New Project",        self.on_new,        "Ctrl+N"),
            ("&Open Project...",    self.on_open,       "Ctrl+O"),
            ("&Save Project",       self.on_save,       "Ctrl+S"),
            ("Save Project &as...", self.on_save_as,    "Ctrl+Shift+S"),
            (None, None, None),
            ("&Exit",               self.close,         "Ctrl+Q"),
        ]:
            if label is None:
                m.addSeparator(); continue
            a = QtGui.QAction(label, self); a.setShortcut(shortcut)
            a.triggered.connect(slot); m.addAction(a)

    def _build_flood_routing_menu(self):
        m = self.menuBar().addMenu("&Flood Routing")
        # Step 1
        a = QtGui.QAction("&1. Reservoir Properties", self)
        a.triggered.connect(lambda: self.open_placeholder("ReservoirProperties"))
        m.addAction(a)
        # Step 2
        a = QtGui.QAction("&2. Spillway Data", self)
        a.triggered.connect(lambda: self.open_placeholder("SpillWayData"))
        m.addAction(a)
        # Step 3
        a = QtGui.QAction("&3. Inflow Data", self)
        a.triggered.connect(lambda: self.open_placeholder("InFlowData"))
        m.addAction(a)
        m.addSeparator()
        # Step 4 - Calculate
        a = QtGui.QAction("&4. Calculate Outflow (Pulse Method)", self)
        a.triggered.connect(lambda: self.open_placeholder("Outflow"))
        m.addAction(a)

    def _build_spillway_menu(self):
        m = self.menuBar().addMenu("&Spillway")
        a = QtGui.QAction("Spillway &Properties (G-Q curves)", self)
        a.triggered.connect(lambda: self.open_placeholder("SpillWayProperties"))
        m.addAction(a)
        a = QtGui.QAction("Spillway &Profile (WES standard)", self)
        a.triggered.connect(lambda: self.open_placeholder("SpillWayProfile"))
        m.addAction(a)

    def _build_cross_sections_menu(self):
        m = self.menuBar().addMenu("&Cross-Sections")
        # 9 cross-section types, matching the original 9 .frm files
        # Preserve the original spellings ("Trangular", "Tropizodal") for fidelity
        for label, key in [
            ("&Rectangular",                    "Rectangular"),
            ("&Trapezoidal",                     "Tropizodal"),
            ("&Circular",                        "Circular"),
            ("&Egg-shaped",                      "EggShape"),
            ("&Horseshoe",                       "HorseShoe"),
            ("&Modified horseshoe",              "ModifiedHorseShoe"),
            ("Rectangular &corner",              "RectangularCorner"),
            ("&Triangular",                      "Trangular"),
            ("Triangular &corner",               "TrangularCorner"),
        ]:
            a = QtGui.QAction(label, self)
            a.triggered.connect(lambda _=False, k=key: self.open_placeholder(k))
            m.addAction(a)

    def _build_calculations_menu(self):
        m = self.menuBar().addMenu("&Calculations")
        for label, key in [
            ("&Spillway Profile",            "SpillWayProfile"),
            ("&Surface Profile (Standard Step)", "SurfaceProfile"),
            ("Cavitation &No.",              "CavitationNo"),
            ("&Air Entrainment",             "AirEntrainment"),
            ("Cavitation &Damage",           "CavitationDamage"),
        ]:
            a = QtGui.QAction(label, self)
            a.triggered.connect(lambda _=False, k=key: self.open_placeholder(k))
            m.addAction(a)

    def _build_show_diagrams_menu(self):
        m = self.menuBar().addMenu("Show &Diagrams")
        for label, slot in [
            ("Show &Spillway Profile",    self.on_show_spillway_profile),
            ("Show &Surface Profile",     self.on_show_surface_profile),
            ("Show &Cavitation No.",      self.on_show_cavitation),
            ("Show Air Entrainment",      self.on_show_air_entrainment),
            ("Show Cavitation Damage",    self.on_show_cavitation_damage),
        ]:
            a = QtGui.QAction(label, self)
            a.triggered.connect(slot)
            m.addAction(a)


    def _build_group_e_menu(self):
        """The 6 unported sub-grid forms (Group E).

        These were sub-grid windows in the original VB6 Cavicuspill,
        showing the underlying data tables for:
          E1. Reservoir elevation-volume
          E2. Inflow hydrograph
          E3. Outflow iteration
          E4. Spillway Q(h) for a selected L
          E5. Spillway profile data
          E6. Outflow hydrograph chart
        """
        from ui.forms.group_e import GROUP_E_FORMS
        m = self.menuBar().addMenu("&Group E")
        for key, (title, _) in GROUP_E_FORMS.items():
            m.addAction(title.replace("&", ""),
                        lambda checked=False, k=key, t=title: self._open_group_e(k, t))

    def _open_group_e(self, key: str, title: str):
        """Open a Group E form, or focus the existing one if already open."""
        from ui.forms.group_e import GROUP_E_FORMS
        # Check if already open
        for sub in self.mdi.subWindowList():
            if sub.windowTitle() == title:
                self.mdi.setActiveSubWindow(sub)
                return
        form_class = GROUP_E_FORMS[key][1]
        sub = form_class(self)
        sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.mdi.addSubWindow(sub)
        sub.show()
        self._refresh_menu_state()


    def _build_help_menu(self):
        m = self.menuBar().addMenu("&Help")
        a = QtGui.QAction("&About Cavicuspill", self)
        a.triggered.connect(self.on_about)
        m.addAction(a)
        a = QtGui.QAction("&User Manual (opens in browser)", self)
        a.triggered.connect(self.on_user_manual)
        m.addAction(a)
        a = QtGui.QAction("&Algorithm Reference", self)
        a.triggered.connect(self.on_algorithm_reference)
        m.addAction(a)

    def _build_admin_menus(self):
        # The original VB6 also has 2 admin menus: ApplicationSteps + About
        m = self.menuBar().addMenu("&Application Steps")
        a = QtGui.QAction("&Step-by-step wizard", self)
        a.triggered.connect(self.on_wizard)
        m.addAction(a)

    # ------------------------------------------------------------------
    #  DIALOG OPENERS
    # ------------------------------------------------------------------
    def open_placeholder(self, form_key: str):
        # Group A dialogs (Phase 1) are real; everything else is a placeholder.
        from ui.forms.reservoir_properties import ReservoirPropertiesDialog
        from ui.forms.spillway_data import SpillwayDataDialog
        from ui.forms.inflow_data import InflowDataDialog
        from ui.forms.spillway_properties import SpillwayPropertiesDialog
        from ui.forms.outflow import OutflowDialog
        from ui.forms.surface_profile import SurfaceProfileDialog
        from ui.forms.spillway_profile import SpillwayProfileDialog
        from ui.forms.cavitation_no import CavitationNoDialog
        from ui.forms.air_entrainment import AirEntrainmentDialog
        from ui.forms.cavitation_damage import CavitationDamageDialog
        from ui.forms.cross_section import make_cross_section_dialog

        if form_key == "ReservoirProperties":
            sub = ReservoirPropertiesDialog()
        elif form_key == "SpillWayData":
            sub = SpillwayDataDialog()
        elif form_key == "InFlowData":
            sub = InflowDataDialog()
        elif form_key == "SpillWayProperties":
            sub = SpillwayPropertiesDialog()
        elif form_key == "Outflow":
            sub = OutflowDialog()
        elif form_key == "SurfaceProfile":
            sub = SurfaceProfileDialog()
        elif form_key == "SpillWayProfile":
            sub = SpillwayProfileDialog()
        elif form_key == "CavitationNo":
            sub = CavitationNoDialog()
        elif form_key == "AirEntrainment":
            sub = AirEntrainmentDialog()
        elif form_key == "CavitationDamage":
            sub = CavitationDamageDialog()
        elif form_key in ("Rectangular", "Tropizodal", "Circular", "EggShape",
                           "HorseShoe", "ModifiedHorseShoe", "RectangularCorner",
                           "Trangular", "TrangularCorner"):
            sub = make_cross_section_dialog(form_key)
        else:
            sub = PlaceholderDialog(form_key)
        sub.setWindowIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogInfoView))
        self.mdi.addSubWindow(sub)
        # Center the sub-window
        if isinstance(sub, QtWidgets.QMdiSubWindow):
            frame = self.mdi.frameGeometry()
            sub.move(frame.width() // 2 - sub.width() // 2,
                     frame.height() // 2 - sub.height() // 2)
        sub.show()
        # When this dialog closes, refresh the menu state (in case any
        # appState flag was set by it).
        if hasattr(sub, "destroyed"):
            sub.destroyed.connect(self._refresh_menu_state)
        return sub

    def _on_subwindow_destroyed(self, *args):
        """Re-enable menu items based on APP_STATE whenever any sub-window
        is closed (since closing a data-entry form is when its state flag
        gets set)."""
        self._refresh_menu_state()

    def _on_subwindow_activated(self, *args):
        """Also refresh on activation (catches cases where state changes
        happen while the window is open)."""
        self._refresh_menu_state()

    # ------------------------------------------------------------------
    #  MENU STATE (mirrors the appState logic in globals.bas)
    # ------------------------------------------------------------------
    def _refresh_menu_state(self):
        # Find all top-level QAction objects and enable/disable them
        # based on APP_STATE.  This mirrors the cascading .Enabled =
        # True/False in the original VB6 code.
        # The Flood Routing > 2. Spillway Data menu is enabled only when
        # the reservoir has been entered.
        # The Flood Routing > 3. Inflow Data menu is enabled only when
        # the spillway data has been entered.
        # The Flood Routing > 4. Calculate Outflow menu is enabled only
        # when both spillway data and inflow data have been entered.
        # The Show Diagrams submenus are enabled when the corresponding
        # calculation has been performed.
        for menu in self.menuBar().findChildren(QtWidgets.QMenu):
            for action in menu.actions():
                text = action.text().lower()
                if "spillway data" in text:
                    # Flood Routing > 2. Spillway Data
                    action.setEnabled(APP_STATE.reservoir)
                if "inflow" in text and "calculate" not in text:
                    # Flood Routing > 3. Inflow Data
                    action.setEnabled(APP_STATE.spillwayData)
                if "outflow" in text and "calculate" in text:
                    # Flood Routing > 4. Calculate Outflow
                    action.setEnabled(APP_STATE.spillwayData and APP_STATE.inFlow)
                if "spillway properties" in text or "profile data" in text:
                    # Spillway > Spillway Properties, Calculations > Profile Data
                    action.setEnabled(APP_STATE.spillwayData)
                if "surface profile" in text and "show" not in text:
                    # Calculations > Surface Profile (Standard Step)
                    action.setEnabled(APP_STATE.spillwayData)
                if "spillway profile" in text and "show" not in text:
                    # Calculations > Spillway Profile (WES)
                    action.setEnabled(APP_STATE.spillwayData)
                if "show" in text and "spillway" in text:
                    action.setEnabled(APP_STATE.spillwayProfile)
                if "show" in text and "surface" in text:
                    action.setEnabled(APP_STATE.surfaceProfile)
                if "show" in text and "cavitation" in text:
                    action.setEnabled(APP_STATE.cavitationNo)

    # ------------------------------------------------------------------
    #  FILE / PROJECT OPERATIONS
    # ------------------------------------------------------------------
    def on_new(self):
        ans = QtWidgets.QMessageBox.question(
            self, "New project",
            "Discard the current project and start a new one?")
        if ans == QtWidgets.QMessageBox.Yes:
            self.mdi.closeAllSubWindows()
            global APP_STATE
            APP_STATE = AppState()
            self._refresh_menu_state()
            self.statusBar().showMessage("New project started", 4000)

    def on_open(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Cavicuspill project", "",
            "Cavicuspill projects (*.cav *.json);;All files (*)")
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self._load_state_from_dict(data)
            self.statusBar().showMessage(f"Opened {os.path.basename(path)}", 5000)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(e))

    def on_save(self):
        if not hasattr(self, "_current_path"):
            self.on_save_as()
            return
        self._save_to(self._current_path)

    def on_save_as(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Cavicuspill project", "",
            "Cavicuspill projects (*.cav);;JSON (*.json);;All files (*)")
        if not path:
            return
        self._save_to(path)
        self._current_path = path

    def _save_to(self, path: str):
        data = self._state_to_dict()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}", 5000)

    def _state_to_dict(self) -> dict:
        s = APP_STATE
        out: dict = {"format": "cavicuspill-py-v0.1",
                     "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
                     "reservoir": None, "spillway": None, "inflow": None}
        if s.reservoir_data is not None:
            out["reservoir"] = {"h0": s.reservoir_data.e,
                                "h":  s.reservoir_data.h.tolist(),
                                "V":  s.reservoir_data.V.tolist()}
        if s.spillway_cfg is not None:
            sw = s.spillway_cfg
            out["spillway"] = {"L_min": sw.L_min, "L_max": sw.L_max,
                                "b": sw.b, "c": sw.c, "deltaT": sw.deltaT}
        if s.inflow is not None:
            out["inflow"] = {"n": s.inflow.n, "t": s.inflow.t_h.tolist(),
                              "Q": s.inflow.Q.tolist()}
        return out

    def _load_state_from_dict(self, d: dict):
        global APP_STATE
        APP_STATE = AppState()
        if d.get("reservoir"):
            r = d["reservoir"]
            APP_STATE.reservoir_data = cav.ReservoirTable(
                e=float(r["h0"]), h=np.array(r["h"]), V=np.array(r["V"]))
            APP_STATE.reservoir = True
        if d.get("spillway"):
            sw = d["spillway"]
            APP_STATE.spillway_cfg = cav.SpillwayConfig(
                L_min=float(sw["L_min"]), L_max=float(sw["L_max"]),
                b=float(sw["b"]), c=float(sw["c"]), deltaT=float(sw["deltaT"]))
            APP_STATE.spillwayData = True
        if d.get("inflow"):
            f = d["inflow"]
            APP_STATE.inflow = cav.InflowHydrograph(
                n=int(f["n"]), t_h=np.array(f["t"]), Q=np.array(f["Q"]))
            APP_STATE.inFlow = True
        self._refresh_menu_state()

    # ------------------------------------------------------------------
    #  SHOW-DIAGRAMS PLACEHOLDERS (these will open real chart windows
    #  embedded with matplotlib in later phases)
    # ------------------------------------------------------------------
    def on_show_spillway_profile(self):
        self.open_placeholder("SpillWayProfile")
    def on_show_surface_profile(self):
        self.open_placeholder("SurfaceProfile")
    def on_show_cavitation(self):
        self.open_placeholder("CavitationNo")
    def on_show_air_entrainment(self):
        self.open_placeholder("AirEntrainment")
    def on_show_cavitation_damage(self):
        self.open_placeholder("CavitationDamage")

    def on_run_all(self):
        QtWidgets.QMessageBox.information(
            self, "Run all",
            "Run-all pipeline is not yet implemented. Use the menus to step "
            "through Reservoir \u2192 Spillway \u2192 Inflow \u2192 Outflow \u2192 Profiles.")

    def on_show_charts(self):
        # Open a single window showing the fresh-example charts from the
        # modernization bonus.  Useful even in the MDI shell.
        win = QtWidgets.QMdiSubWindow()
        win.setWindowTitle("Charts (modernization bonus — fresh example)")
        win.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        win.resize(900, 600)

        # Build a tabbed chart view on the fly from the PNG files
        w = QtWidgets.QTabWidget()
        chart_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "output", "fresh_example")
        if os.path.isdir(chart_dir):
            for fn in sorted(os.listdir(chart_dir)):
                if fn.endswith(".png"):
                    label = QtWidgets.QLabel()
                    label.setPixmap(QtGui.QPixmap(os.path.join(chart_dir, fn))
                                    .scaledToWidth(820, QtCore.Qt.SmoothTransformation))
                    label.setAlignment(QtCore.Qt.AlignCenter)
                    w.addTab(label, fn.replace("fresh_", "").replace(".png", "").replace("_", " ").title())
        if w.count() == 0:
            w.addTab(QtWidgets.QLabel("No charts found in output/fresh_example/"),
                     "No charts")
        win.setWidget(w)
        self.mdi.addSubWindow(win)
        win.show()

    def on_wizard(self):
        QtWidgets.QMessageBox.information(
            self, "Wizard",
            "Step-by-step wizard is not yet implemented. Use the menus.")

    def on_user_manual(self):
        QtWidgets.QMessageBox.information(
            self, "User manual",
            "The user manual is supplied in the supplementary archive as "
            "USER_MANUAL.md and is also available at the IUST Department of "
            "Civil Engineering.")

    def on_algorithm_reference(self):
        QtWidgets.QMessageBox.information(
            self, "Algorithm reference",
            "The algorithm reference is supplied in the supplementary archive "
            "as MODERNIZATION.md, with a 1:1 mapping from each Python "
            "function to the original VB6 source line.")

    def on_about(self):
        """A richer About dialog with: app icon, author info, a
        ready-to-paste BibTeX citation, the list of ported forms, and
        the full MIT license text.  Replaces the original QMessageBox
        'about' with a 4-tab QDialog.
        """
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("About Cavicuspill-Py")
        dlg.resize(640, 720)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)

        # ----- App icon + title block -----
        h = QtWidgets.QHBoxLayout()
        icon_lbl = QtWidgets.QLabel()
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "cavicuspill.png")
        if os.path.exists(icon_path):
            pix = QtGui.QPixmap(icon_path).scaledToWidth(
                80, QtCore.Qt.SmoothTransformation)
            icon_lbl.setPixmap(pix)
        h.addWidget(icon_lbl, 0, QtCore.Qt.AlignTop)

        title = QtWidgets.QLabel()
        title.setTextFormat(QtCore.Qt.RichText)
        title.setText(
            "<h2 style='color:#1A3A6C; margin:0'>Cavicuspill</h2>"
            "<p style='color:#666; font-style:italic; margin:2px 0'>"
            "<em>Cavitation in Chutes and Spillways</em></p>"
            "<p style='margin:0'>A modern Python 3 / PySide6 port of the original "
            "2005 Visual Basic 6.0 workbench.</p>"
        )
        title.setWordWrap(True)
        h.addWidget(title, 1)
        v.addLayout(h)

        # ----- Tabs -----
        tabs = QtWidgets.QTabWidget()
        v.addWidget(tabs, 1)

        # Tab 1: About
        about_w = QtWidgets.QWidget(); about_v = QtWidgets.QVBoxLayout(about_w)
        about_v.setContentsMargins(8, 8, 8, 8)
        about_v.addWidget(QtWidgets.QLabel(
            "<p style='margin:0 0 6px 0'><b>Author:</b> Abbas A. Hebah "
            "&nbsp;&middot;&nbsp; Department of Civil Engineering, "
            "Iran University of Science and Technology (IUST)</p>"
            "<p style='margin:0 0 6px 0'><b>Email:</b> "
            "<a href='mailto:abbas74.hebah@gmail.com'>abbas74.hebah@gmail.com</a></p>"
            "<p style='margin:0 0 6px 0'><b>License:</b> MIT &mdash; "
            "Copyright &copy; 2026 Abbas A. Hebah. All rights reserved.</p>"
            "<p style='margin:0 0 6px 0'><b>Version:</b> 1.0 "
            "(all 4 groups, 19/25 forms ported)</p>"
            "<p style='margin:0 0 6px 0'><b>Build:</b> Python "
            + sys.version.split()[0] + ", PySide6 "
            + QtCore.__version__ + ", NumPy "
            + __import__('numpy').__version__ + ", Matplotlib "
            + __import__('matplotlib').__version__ + "</p>"
            "<p style='margin:6px 0 0 0'><b>Original 2005 release:</b> preserved "
            "unmodified in the supplementary archive "
            "(<code>Cavicuspill_source.zip</code>, MIT License).</p>"
        ))
        about_v.addStretch(1)
        tabs.addTab(about_w, "About")

        # Tab 2: Citation
        cite_w = QtWidgets.QWidget(); cite_v = QtWidgets.QVBoxLayout(cite_w)
        cite_v.setContentsMargins(8, 8, 8, 8)
        cite_lbl = QtWidgets.QLabel()
        cite_lbl.setTextFormat(QtCore.Qt.RichText)
        cite_lbl.setText(
            "<p style='margin:0 0 6px 0'><b>If you use Cavicuspill-Py in a "
            "publication, please cite the following:</b></p>"
            "<pre style='background:#F4F1E8; padding:8px; border:1px solid #888; "
            "font-family:Courier New,monospace; font-size:9pt;'>"
            "@article{hebah2026cavicuspill,\n"
            "  title  = {Cavicuspill: An integrated Visual Basic 6.0 workbench\n"
            "            for spillway cavitation-risk assessment, air-entrainment,\n"
            "            and cavitation-damage analysis},\n"
            "  author = {Hebah, Abbas A.},\n"
            "  journal = {SoftwareX},\n"
            "  year   = {2026},\n"
            "  note   = {Modernized to Python 3 / PySide6; original release 2005}\n"
            "}"
            "</pre>"
            "<p style='margin:8px 0 0 0'><b>Underlying algorithms (please also "
            "cite these as appropriate):</b></p>"
            "<ul style='margin:4px 0 4px 20px; padding:0; font-size:9pt'>"
            "<li>Falvey, H. T. (1990). <em>Cavitation in chutes and spillways.</em> "
            "USBR Engineering Monograph No. 42. &mdash; cavitation index, "
            "singular-roughness, uniform-roughness.</li>"
            "<li>U.S. Bureau of Reclamation (1987). <em>Design of small dams.</em> "
            "3rd ed. &mdash; WES standard overflow-spillway K, P coefficients.</li>"
            "<li>Chow, V. T. (1959). <em>Open-channel hydraulics.</em> McGraw-Hill. "
            "&mdash; Standard Step Method.</li>"
            "<li>Chaudhry, M. H. (2008). <em>Open-channel flow.</em> 2nd ed. Springer. "
            "&mdash; direct-step Newton iteration.</li>"
            "<li>Young, F. R. (1989). <em>Cavitation.</em> McGraw-Hill. "
            "&mdash; pure-water thermophysical properties.</li>"
            "</ul>"
        )
        cite_lbl.setWordWrap(True)
        cite_v.addWidget(cite_lbl)
        cite_v.addStretch(1)
        tabs.addTab(cite_w, "Citation")

        # Tab 3: Forms (19 ported)
        forms_w = QtWidgets.QWidget(); forms_v = QtWidgets.QVBoxLayout(forms_w)
        forms_v.setContentsMargins(8, 8, 8, 8)
        forms_lbl = QtWidgets.QLabel()
        forms_lbl.setTextFormat(QtCore.Qt.RichText)
        forms_lbl.setText(
            "<p style='margin:0 0 6px 0'><b>19 of 25 original VB6 forms ported</b></p>"
            "<p style='margin:0 0 4px 0'><b>Group A &mdash; data entry (4):</b></p>"
            "<ol style='margin:0 0 6px 20px; padding:0; font-size:9pt'>"
            "<li>Reservoir Properties (ReservoirProperties.frm)</li>"
            "<li>Spillway Data (SpillWayData.frm)</li>"
            "<li>Inflow Data (InFlowData.frm)</li>"
            "<li>Spillway Properties / G-Q viewer (SpillWayProperties.frm)</li>"
            "</ol>"
            "<p style='margin:0 0 4px 0'><b>Group B &mdash; calculation + charts (3):</b></p>"
            "<ol start='5' style='margin:0 0 6px 20px; padding:0; font-size:9pt'>"
            "<li>Outflow / Pulse-Method (Outflow.frm + OutflowDiagram.frm)</li>"
            "<li>WES Spillway Profile (SpillWayProfile.frm)</li>"
            "<li>Surface Profile / Standard Step (SurfaceProfile.frm + ProfileData.frm)</li>"
            "</ol>"
            "<p style='margin:0 0 4px 0'><b>Group C &mdash; cavitation (3):</b></p>"
            "<ol start='8' style='margin:0 0 6px 20px; padding:0; font-size:9pt'>"
            "<li>Cavitation No. (CavitationNo.frm)</li>"
            "<li>Air Entrainment (AirEntrainment.frm)</li>"
            "<li>Cavitation Damage (no .frm in source; integrated module)</li>"
            "</ol>"
            "<p style='margin:0 0 4px 0'><b>Group D &mdash; cross-sections (9):</b></p>"
            "<ol start='11' style='margin:0 0 6px 20px; padding:0; font-size:9pt'>"
            "<li>Rectangular, 12. Trapezoidal, 13. Circular, 14. Egg-shaped, "
            "15. Horseshoe, 16. Modified horseshoe, 17. Rectangular corner, "
            "18. Triangular, 19. Triangular corner</li>"
            "</ol>"
            "<p style='margin:0 0 0 0; font-size:8.5pt; color:#666; font-style:italic'>"
            "The 6 unported forms (OutflowDiagram, OutFlowDataGrid, "
            "InFlowDataGrid, ReservoirPropertiesGrid, SpillWayDataGrid, "
            "ProfileData) are sub-grids that are now rendered as part of "
            "the main forms via the embedded matplotlib charts and "
            "QTableWidget data grids.</p>"
        )
        forms_lbl.setWordWrap(True)
        forms_v.addWidget(forms_lbl)
        forms_v.addStretch(1)
        tabs.addTab(forms_w, "Ported forms (19)")

        # Tab 4: License
        lic_w = QtWidgets.QWidget(); lic_v = QtWidgets.QVBoxLayout(lic_w)
        lic_v.setContentsMargins(8, 8, 8, 8)
        lic_lbl = QtWidgets.QLabel()
        lic_lbl.setTextFormat(QtCore.Qt.RichText)
        lic_lbl.setText(
            "<pre style='background:#F4F1E8; padding:8px; border:1px solid #888; "
            "font-family:Courier New,monospace; font-size:9pt;'>"
            "MIT License\n"
            "\n"
            "Copyright (c) 2026 Abbas A. Hebah\n"
            "\n"
            "Permission is hereby granted, free of charge, to any person obtaining "
            "a copy of this software and associated documentation files (the "
            "\"Software\"), to deal in the Software without restriction, including "
            "without limitation the rights to use, copy, modify, merge, publish, "
            "distribute, sublicense, and/or sell copies of the Software, and to "
            "permit persons to whom the Software is furnished to do so, subject "
            "to the following conditions:\n"
            "\n"
            "The above copyright notice and this permission notice shall be "
            "included in all copies or substantial portions of the Software.\n"
            "\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, "
            "EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF "
            "MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. "
            "IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY "
            "CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, "
            "TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE "
            "SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."
            "</pre>"
        )
        lic_lbl.setWordWrap(True)
        lic_v.addWidget(lic_lbl)
        lic_v.addStretch(1)
        tabs.addTab(lic_w, "License (MIT)")

        # ----- Bottom button row -----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_copy = QtWidgets.QPushButton("Copy BibTeX")
        btn_copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(
            "@article{hebah2026cavicuspill,\n"
            "  title  = {Cavicuspill: An integrated Visual Basic 6.0 workbench\n"
            "            for spillway cavitation-risk assessment, air-entrainment,\n"
            "            and cavitation-damage analysis},\n"
            "  author = {Hebah, Abbas A.},\n"
            "  journal = {SoftwareX},\n"
            "  year   = {2026}\n"
            "}"))
        btn_row.addWidget(btn_copy)
        btn_close = QtWidgets.QPushButton("&Close")
        btn_close.setDefault(True)
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        dlg.exec()


# =============================================================================
#  ENTRY POINT
# =============================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Cavicuspill-Py &mdash; the modern Python 3 / PySide6 port "
                    "of the original 2005 Visual Basic 6.0 Cavicuspill workbench.")
    parser.add_argument("--no-screenshot", action="store_true",
                        help="Skip the post-launch screenshot")
    parser.add_argument("--screenshot", default="/tmp/cav_qt.png",
                        help="Where to save the post-launch screenshot (PNG)")
    args = parser.parse_args()

    QtCore.QCoreApplication.setOrganizationName("IUST")
    QtCore.QCoreApplication.setApplicationName("Cavicuspill-Py")
    QtCore.QCoreApplication.setApplicationVersion("0.1")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    win = CavicuspillMainWindow()
    win.show()

    # Take a screenshot of the main window 1.5s after launch
    if not args.no_screenshot:
        def take_screenshot():
            pix = win.grab()
            pix.save(args.screenshot)
            print(f"Screenshot saved to {args.screenshot}")
        QtCore.QTimer.singleShot(1500, take_screenshot)
        # Optional: auto-quit 2.5s after the screenshot
        QtCore.QTimer.singleShot(2500, app.quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
