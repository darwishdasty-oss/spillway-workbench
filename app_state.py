"""
app_state.py - Unified application state shared between Cavicuspill and EM-Py.

This module is the **bridge** between the two domains:
  - Cavicuspill writes spillway design data (reservoir, spillway config,
    inflow, surface profile, cavitation result)
  - EM-Py reads that geometry and computes water surface profile, cavitation
    index, damage rates

A single APP_STATE instance is shared across the MDI shell so:
  - A spillway designed in Cavicuspill can be analyzed in EM-Py with one click
  - A geometry file loaded in EM-Py can be inspected via Cavicuspill's
    cross-section forms
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any, Optional

# Lazy imports to avoid circular dependencies
def _cav():
    # The AppState lives in cavicuspill.ui.mdi_main
    import cavicuspill.ui.mdi_main as cav_mdi
    # Re-export under the cavicuspill namespace for convenience
    import cavicuspill as _c
    if not hasattr(_c, "AppState"):
        _c.AppState = cav_mdi.AppState
        _c.APP_STATE = cav_mdi.APP_STATE
    return _c

def _em():
    import em_py.em_data
    return em_py.em_data


@dataclass
class SpillwayWorkbenchState:
    """The single shared APP_STATE for both Cavicuspill and EM-Py.

    Cavicuspill fields (mostly booleans + design data):
        reservoir_loaded, spillway_loaded, inFlow_loaded, ...
    EM-Py fields (geometry + analysis results):
        em_geometry (GeometryFile), em_ws_output (WSOutput), ...
    Cross-bridge fields (used to translate one to the other):
        bridge_invert_profile: list of (sta, invert) from Cavicuspill
        bridge_cross_section: dict with WES design (P, H, L, ...)
    """
    # --- Cavicuspill state (mirrors cavicuspill's AppState) ---
    cav: Any = None      # cavicuspill.AppState instance (lazy)

    # --- EM-Py state ---
    em_geometry: Any = None         # em_data.GeometryFile (loaded from GLENIN etc.)
    em_ws_output: Any = None        # em_data.WSOutput (last WS77 run)
    em_ecn_input: Any = None        # em_data.ECNInput
    em_plot_data: Any = None        # em_data.PlotFile
    em_bl_data: Any = None          # em_data.BLRecord
    em_hydrograph: Any = None       # inflow hydrograph for DINDX
    em_last_data_dir: str = ""

    # --- Cross-bridge ---
    bridge_invert_profile: list = field(default_factory=list)
    bridge_cross_section: dict = field(default_factory=dict)
    bridge_design_summary: str = ""

    # --- UI state ---
    last_dir: str = ""
    current_project: str = ""
    last_export_path: str = ""

    def get_cav_state(self):
        """Return the cavicuspill AppState, creating it if needed."""
        if self.cav is None:
            self.cav = _cav().AppState()
        return self.cav

    def bridge_from_cav_to_em(self) -> bool:
        """Build an EM-Py geometry from the Cavicuspill design output.

        Returns True on success, False if the Cavicuspill state is incomplete.

        The bridge translates:
          - The designed invert profile (list of (sta, invert)) from
            Cavicuspill's spillway design into EM-Py station records
          - The chosen cross-section (P, H, L) into EM-Py section geometry
          - The design Q (peak inflow) into the EM-Py geometry Q
        """
        cav_state = self.get_cav_state()
        if not cav_state.profileData or not cav_state.spillwayProfile:
            return False
        # Pull the invert profile from the Cavicuspill output
        # (whatever was the most recent design)
        if not self.bridge_invert_profile:
            return False
        # Build the EM-Py GeometryFile
        em_geom = _em().GeometryFile()
        em_geom.title = "From Cavicuspill"
        em_geom.q = cav_state.wes_design.get("Q", 100.0) if cav_state.wes_design else 100.0
        em_geom.y0 = cav_state.wes_design.get("P", 5.0) if cav_state.wes_design else 5.0
        em_geom.slope_initial = 0.5  # default 1V:2H
        em_geom.k_s = 0.0003  # 0.3 mm default
        # Build station records
        em_geom.stations = []
        em_geom.nsta = len(self.bridge_invert_profile)
        for i, (sta, invert) in enumerate(self.bridge_invert_profile):
            rec = _em().StationRecord(
                sta=float(sta),
                invert=float(invert),
                geom_code1=1,  # rectangular default
                width=self.bridge_cross_section.get("Lc", 30.0),
                r1=0.0, r2=0.0, cl_height=0.0, side_slope=0.0,
                rad_curv=0.0,
            )
            em_geom.stations.append(rec)
        self.em_geometry = em_geom
        return True

    def bridge_from_em_to_cav(self) -> bool:
        """Update the Cavicuspill design summary from an EM-Py geometry.

        Used when the user has an EM-Py geometry file (Glen Canyon, Blue Mesa)
        and wants to view the cross-section design summary in Cavicuspill.
        """
        if self.em_geometry is None or len(self.em_geometry.stations) == 0:
            return False
        self.bridge_invert_profile = [
            (s.sta, s.invert) for s in self.em_geometry.stations
        ]
        # Try to extract a representative cross-section
        if self.em_geometry.stations:
            mid = self.em_geometry.stations[len(self.em_geometry.stations) // 2]
            self.bridge_cross_section = {
                "Lc": mid.width if mid.width > 0 else 30.0,
                "Q": self.em_geometry.q,
            }
        cav_state = self.get_cav_state()
        cav_state.wes_design = {
            "L": self.bridge_cross_section.get("Lc", 30.0),
            "Q": self.em_geometry.q,
            "P": 5.0,
            "H": 2.0,
        }
        return True

    def summary(self) -> str:
        """A short summary of what's loaded."""
        lines = []
        cav_state = self.get_cav_state()
        if cav_state.reservoir:
            lines.append(f"Cavicuspill: Reservoir loaded ({len(cav_state.reservoir_data.h) if cav_state.reservoir_data else 0} points)")
        if cav_state.spillwayData:
            lines.append("Cavicuspill: Spillway data loaded")
        if cav_state.inFlow:
            lines.append("Cavicuspill: Inflow data loaded")
        if cav_state.surfaceProfile:
            lines.append("Cavicuspill: Surface profile computed")
        if cav_state.cavitationDamage:
            lines.append("Cavicuspill: Cavitation damage computed")
        if cav_state.airEntrainment:
            lines.append("Cavicuspill: Air entrainment computed")
        if self.em_geometry is not None and len(self.em_geometry.stations) > 0:
            lines.append(f"EM-Py: Geometry loaded ({len(self.em_geometry.stations)} stations, Q={self.em_geometry.q:.1f} m^3/s)")
        if self.em_ws_output is not None:
            lines.append("EM-Py: WS77 water surface profile computed")
        if not lines:
            return "No data loaded yet."
        return "\n".join(lines)


APP_STATE = SpillwayWorkbenchState()
