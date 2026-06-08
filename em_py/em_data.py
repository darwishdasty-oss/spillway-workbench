"""
em_data.py - Data file format readers for the Falvey "Cavitation Programs" toolset.

The original DOS Fortran 77 programs (1987, 1990) read fixed-column ASCII files.
This module provides Python readers and writers for each of the 8 data file
formats used by the original toolset.

References:
    Henry T. Falvey, "Cavitation in Chutes and Spillways",
    Engineering Monograph No. 42, USBR, 1990.
    Henry T. Falvey, "Cavitation of Bureau of Reclamation Spillways",
    USBR, June 1987.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


# =============================================================================
# Common utilities
# =============================================================================

def _to_float(s) -> float:
    s = str(s).strip()
    if not s:
        return 0.0
    s = s.replace('D', 'E').replace('d', 'e')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _to_int(s) -> int:
    s = str(s).strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


# =============================================================================
# Station geometry record
# =============================================================================

@dataclass
class StationRecord:
    sta: float
    invert: float
    width: float = 0.0
    side_slope: float = 0.0
    r1: float = 0.0
    r2: float = 0.0
    cl_height: float = 0.0
    lower_r: float = 0.0
    wall_c2: float = 0.0
    rad_curv: float = 0.0
    roughness: float = 0.0
    geom_code1: int = 0
    geom_code2: int = 0


@dataclass
class GeometryFile:
    q: float = 0.0
    y0: float = 0.0
    k_s: float = 0.0
    n_tech: int = 0
    n_units: int = 0
    slope_initial: float = 0.0
    wse_initial: float = 0.0
    reservoir_elev: float = 0.0
    title: str = ""
    nsta: int = 0
    stations: List[StationRecord] = field(default_factory=list)

    @property
    def is_si(self) -> bool:
        return self.n_units == 0

    def write(self, path: str) -> None:
        with open(path, 'w', encoding='latin-1') as f:
            f.write(f"{self.q:12.3f}{self.y0:10.4f}{self.k_s:11.5f}"
                    f"{self.n_tech:3d}{self.n_units:3d}"
                    f"{self.slope_initial:10.6f}{self.wse_initial:11.3f}"
                    f"{self.reservoir_elev:12.3f}\n")
            f.write(f"{self.title:60s}\n")
            f.write(f"{self.nsta:4d}\n")
            for s in self.stations:
                f.write(f"{s.geom_code1:5d}{s.geom_code2:4d}\n")
                if s.geom_code1 == 5:
                    f.write(f"  {s.sta:10.3f}{s.invert:11.3f}{s.width:10.3f}"
                            f"{s.r1:11.3f}{s.r2:11.3f}{s.cl_height:11.3f}"
                            f"{s.rad_curv:10.1f}{s.roughness:10.6f}\n")
                else:
                    f.write(f"  {s.sta:10.3f}{s.invert:11.3f}{s.width:10.3f}"
                            f"{s.rad_curv:10.1f}{s.roughness:10.6f}\n")


def read_geometry_file(path: str) -> GeometryFile:
    with open(path, 'r', encoding='latin-1') as f:
        lines = f.readlines()
    if len(lines) < 4:
        raise ValueError(f"{path}: too few lines")

    parts = lines[0].split()
    # Some files have 8 numbers on line 1; others (e.g. GLENECN) have 7 on
    # line 1 and reservoir_elev on line 2.
    if len(parts) >= 8:
        reservoir = _to_float(parts[7]) if len(parts) > 7 else 0.0
    else:
        # Read line 2 as reservoir elevation
        reservoir = _to_float(lines[1].strip()) if len(lines) > 1 else 0.0
    g = GeometryFile(
        q=_to_float(parts[0]) if len(parts) > 0 else 0.0,
        y0=_to_float(parts[1]) if len(parts) > 1 else 0.0,
        k_s=_to_float(parts[2]) if len(parts) > 2 else 0.0,
        n_tech=_to_int(parts[3]) if len(parts) > 3 else 0,
        n_units=_to_int(parts[4]) if len(parts) > 4 else 0,
        slope_initial=_to_float(parts[5]) if len(parts) > 5 else 0.0,
        wse_initial=_to_float(parts[6]) if len(parts) > 6 else 0.0,
        reservoir_elev=reservoir,
    )
    if len(parts) >= 8:
        g.title = lines[1].rstrip()
        g.nsta = _to_int(lines[2].strip())
        start = 3
    else:
        # 7+1 layout: title is on line 2, nsta on line 3
        g.title = lines[2].rstrip() if len(lines) > 2 else ''
        g.nsta = _to_int(lines[3].strip()) if len(lines) > 3 else 0
        start = 4

    i = 3
    while i < len(lines) and len(g.stations) < g.nsta:
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        toks = lines[i].split()
        if len(toks) < 2:
            i += 1
            continue
        ic1 = _to_int(toks[0])
        ic2 = _to_int(toks[1])
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        toks = lines[i].split()
        s = StationRecord(
            sta=_to_float(toks[0]) if toks else 0.0,
            invert=_to_float(toks[1]) if len(toks) > 1 else 0.0,
            geom_code1=ic1,
            geom_code2=ic2,
        )
        if ic1 == 5:
            if len(toks) >= 7:
                # 1-line format: 9 numbers (sta, invert, w_or_R2, ss_or_CL,
                # R1, R2, CL_H, R_curv, rough)
                s.width = _to_float(toks[2]) if len(toks) > 2 else 0.0
                s.side_slope = _to_float(toks[3]) if len(toks) > 3 else 0.0
                s.r1 = _to_float(toks[4]) if len(toks) > 4 else 0.0
                s.r2 = _to_float(toks[5]) if len(toks) > 5 else 0.0
                s.cl_height = _to_float(toks[6]) if len(toks) > 6 else 0.0
                s.rad_curv = _to_float(toks[7]) if len(toks) > 7 else 0.0
                s.roughness = _to_float(toks[8]) if len(toks) > 8 else 0.0
            else:
                # 2-line format: 6 on this line, 3 on next
                s.width = _to_float(toks[2]) if len(toks) > 2 else 0.0
                s.side_slope = _to_float(toks[3]) if len(toks) > 3 else 0.0
                s.r1 = _to_float(toks[4]) if len(toks) > 4 else 0.0
                s.r2 = _to_float(toks[5]) if len(toks) > 5 else 0.0
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i < len(lines):
                    toks2 = lines[i].split()
                    s.cl_height = _to_float(toks2[0]) if len(toks2) > 0 else 0.0
                    s.rad_curv = _to_float(toks2[1]) if len(toks2) > 1 else 0.0
                    s.roughness = _to_float(toks2[2]) if len(toks2) > 2 else 0.0
        elif len(toks) >= 5:
            s.width = _to_float(toks[2]) if len(toks) > 2 else 0.0
            s.rad_curv = _to_float(toks[3]) if len(toks) > 3 else 0.0
            s.roughness = _to_float(toks[4]) if len(toks) > 4 else 0.0
        g.stations.append(s)
        i += 1

    return g


# =============================================================================
# Water surface profile output reader (GLENOUT)
# =============================================================================

@dataclass
class ProfileRow:
    sta: float
    invert: float
    slope: float
    depth: float
    velocity: float
    piez_head: float
    energy_grade: float
    q_air_over_q_water: float
    profile: str
    normal_depth: float
    critical_depth: float
    boundary_layer: float


@dataclass
class CavitationRow:
    sta: float
    flow_sigma: float
    sigma_uniform_roughness: float
    chamfer_low: int
    chamfer_high: int
    circ_arc_quarter: float
    circ_arc_half: float
    circ_arc_one: float
    ninety_deg_quarter: float
    ninety_deg_half: float
    ninety_deg_one: float
    turbulence: float


@dataclass
class WSOutput:
    title: str
    q: float
    y0: float
    roughness_mm: float
    manning_n: float
    egl_initial: Optional[float] = None
    profile_rows: List[ProfileRow] = field(default_factory=list)
    cavitation_rows: List[CavitationRow] = field(default_factory=list)


_PROFILE_RE = re.compile(
    r"^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
)

_CAV_RE = re.compile(
    r"^\s*(\d+\.\d+)\s+(\.\d+|\d+\.\d+)\s+(\.\d+|\d+\.\d+)\s+(\d+)\s+TO\s+(\d+)\s+"
    r"(\S+E[+\-]\d+)\s+(\S+E[+\-]\d+)\s+(\S+E[+\-]\d+)\s+"
    r"(\S+E[+\-]\d+)\s+(\S+E[+\-]\d+)\s+(\S+E[+\-]\d+)\s+"
    r"(\.\d+|\d+\.\d+)\s*$"
)


def read_ws_output(path: str) -> WSOutput:
    out = WSOutput(title="", q=0, y0=0, roughness_mm=0, manning_n=0)
    with open(path, 'r', encoding='latin-1') as f:
        text = f.read()

    m = re.search(r"Q\s*=\s*(\S+)\s+CMS\s+INITIAL DEPTH\s*=\s*(\S+)\s+M\s+RUGOSITY\s*=\s*(\S+)\s+MM\s+N\s*=\s*(\S+)", text)
    if m:
        out.q = _to_float(m.group(1))
        out.y0 = _to_float(m.group(2))
        out.roughness_mm = _to_float(m.group(3))
        out.manning_n = _to_float(m.group(4))

    m = re.search(r"ENERGY GRADE LINE AT BEGINNING OF BOUNDARY LAYER\s*\n\s*(\S+)", text)
    if m:
        out.egl_initial = _to_float(m.group(1))

    # Title is the line right after the leading "1" (input unit flag)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("Q ="):
            if i > 0:
                out.title = lines[i - 1].strip()
            break

    # Parse profile rows
    in_profile = False
    in_cav = False
    for line in text.splitlines():
        if "STATION   INVERT ELEV   SLOPE" in line:
            in_profile = True
            in_cav = False
            continue
        if "CAVITATION CHARACTERISTICS" in line:
            in_profile = False
            in_cav = True
            continue
        m = _PROFILE_RE.match(line)
        if m and in_profile:
            out.profile_rows.append(ProfileRow(
                sta=_to_float(m.group(1)),
                invert=_to_float(m.group(2)),
                slope=_to_float(m.group(3)),
                depth=_to_float(m.group(4)),
                velocity=_to_float(m.group(5)),
                piez_head=_to_float(m.group(6)),
                energy_grade=_to_float(m.group(7)),
                q_air_over_q_water=_to_float(m.group(8)),
                profile=m.group(9),
                normal_depth=_to_float(m.group(10)),
                critical_depth=_to_float(m.group(11)),
                boundary_layer=_to_float(m.group(12)),
            ))
            continue
        m = _CAV_RE.match(line)
        if m and in_cav:
            out.cavitation_rows.append(CavitationRow(
                sta=_to_float(m.group(1)),
                flow_sigma=_to_float(m.group(2)),
                sigma_uniform_roughness=_to_float(m.group(3)),
                chamfer_low=_to_int(m.group(4)),
                chamfer_high=_to_int(m.group(5)),
                circ_arc_quarter=_to_float(m.group(6)),
                circ_arc_half=_to_float(m.group(7)),
                circ_arc_one=_to_float(m.group(8)),
                ninety_deg_quarter=_to_float(m.group(9)),
                ninety_deg_half=_to_float(m.group(10)),
                ninety_deg_one=_to_float(m.group(11)),
                turbulence=_to_float(m.group(12)),
            ))

    return out


# =============================================================================
# Plot-ready data file reader (GLENPLOT)
# =============================================================================

@dataclass
class PlotFile:
    title: str
    n_plots: int
    n_sta: int
    discharge: float
    stations: List[float] = field(default_factory=list)
    elevations: List[float] = field(default_factory=list)
    flow_depths: List[float] = field(default_factory=list)
    piez_pressures: List[float] = field(default_factory=list)
    velocities: List[float] = field(default_factory=list)
    energies: List[float] = field(default_factory=list)
    boundary_layers: List[float] = field(default_factory=list)


def read_plot_file(path: str) -> PlotFile:
    with open(path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    title = lines[0].rstrip() if lines else ""
    n_plots = n_sta = 0
    discharge = 0.0
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("NO OF PLOTS"):
            toks = line.split()
            n_plots = _to_int(toks[3]) if len(toks) > 3 else 0
            n_sta = _to_int(toks[6]) if len(toks) > 6 else 0
        elif line == "DISCHARGE" and i + 1 < len(lines):
            discharge = _to_float(lines[i + 1])
            i += 1
        elif line in ("STATION", "ELEVATION", "FLOW DEPTH", "PIEZOMETRIC PRESSURE",
                      "VELOCITY", "ENERGY", "BOUNDARY LAYER THICKNESS"):
            block = []
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().isalpha() and " " not in lines[i].strip()[:2]:
                block.extend(_to_float(t) for t in lines[i].split())
                i += 1
            continue
        i += 1

    pf = PlotFile(title=title, n_plots=n_plots, n_sta=n_sta, discharge=discharge)
    return pf


# =============================================================================
# ECAVNO input file reader (ECNDAT + GLENECN)
# =============================================================================

@dataclass
class ECNInput:
    title: str
    """Parsed from ECNDAT (one-line problem definition)."""
    q: float
    y0: float
    k_s: float
    n_tech: int
    n_units: int
    slope_initial: float
    reservoir_elev: float
    p_atm: float
    p_vapor: float
    g: float
    sigma_target: float
    assumption: str  # "N"=potential flow, "Y"=solid body rotation
    nsta: int = 0
    stations: List[StationRecord] = field(default_factory=list)

    @property
    def is_si(self) -> bool:
        return self.n_units == 0


def read_ecn_input(ecndat_path: str, glenecn_path: str) -> ECNInput:
    """Read both ECNDAT (problem definition) and GLENECN (station geometry)."""
    with open(ecndat_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()
    title = lines[0].rstrip() if lines else ""
    assumption = lines[1].strip() if len(lines) > 1 else "N"
    nums = lines[2].split() if len(lines) > 2 else []
    # ECNDAT third line: 9 numbers in unknown order
    # (reservoir elevation, integration interval, delta head, g, p_atm, p_vapor,
    #  convergence, unit discharge, head_from_reservoir)
    # Default values for known quantities
    p_atm_default = 101325.0  # 101325 Pa
    p_vapor_default = 2330.0  # Pa at 20 C
    g_default = 9.8076
    sigma_default = 0.20  # typical target
    e = ECNInput(
        title=title,
        q=0.0,
        y0=0.0,
        k_s=0.0,
        n_tech=0,
        n_units=0,
        slope_initial=0.0,
        reservoir_elev=1127.760 if len(nums) < 9 else _to_float(nums[8]),
        p_atm=p_atm_default,
        p_vapor=p_vapor_default,
        g=g_default,
        sigma_target=sigma_default,
        assumption=assumption,
        nsta=0,
    )
    # Read geometry from GLENECN (same format as GLENIN)
    g = read_geometry_file(glenecn_path)
    e.q = g.q
    e.y0 = g.y0
    e.k_s = g.k_s
    e.slope_initial = g.slope_initial
    e.nsta = g.nsta
    e.stations = g.stations
    return e


# =============================================================================
# Boundary layer data reader (GLENHY)
# =============================================================================

@dataclass
class BLProfile:
    """One (y, eta) pair in a boundary layer velocity profile."""
    y: float
    eta: float


@dataclass
class BLRecord:
    title: str
    """Title of the measurement (e.g. 'GLEN CANYON LEFT SPILLWAY - STA 24+25')."""
    n_profiles: int
    """Number of velocity profiles at this station."""
    profiles: List[List[BLProfile]] = field(default_factory=list)
    """Each profile is a list of (y, eta) points."""
    discharges: List[Tuple[str, str, float]] = field(default_factory=list)
    """List of (date, source, Q) for each discharge measurement at this station."""


def read_bl_file(path: str) -> BLRecord:
    """Read a boundary layer profile file (GLENHY or HYDROL format).
    
    Format:
      Line 1: title
      Line 2: n_profiles
      Lines 3..: pairs of (y, eta) per profile, separated by '0,0' terminator
      Then a date, Q-value series (one per line, with month/day/year comment lines)
    """
    with open(path, 'r', encoding='latin-1') as f:
        text = f.read()

    lines = text.splitlines()
    rec = BLRecord(title=lines[0].rstrip() if lines else "", n_profiles=0, profiles=[])
    if len(lines) > 1:
        rec.n_profiles = _to_int(lines[1].strip())

    # Parse profile points
    i = 2
    current: List[BLProfile] = []
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # A profile is a comma-separated (y, eta) pair
        if "," in line and " " not in line.replace(",", " "):
            toks = line.replace(",", " ").split()
            if len(toks) == 2:
                try:
                    y, eta = float(toks[0]), float(toks[1])
                    if y == 0 and eta == 0:
                        if current:
                            rec.profiles.append(current)
                            current = []
                    else:
                        current.append(BLProfile(y=y, eta=eta))
                except ValueError:
                    pass
        i += 1
    if current:
        rec.profiles.append(current)

    return rec


# =============================================================================
# Quick validation: load all bundled sample files
# =============================================================================

def load_sample_data(name: str = "glen_canyon"):
    """Return a dict of all sample data files for the given project.

    Available: "glen_canyon" (GLENIN/GLENOUT/...), "blue_mesa" (SPWY), "hoover" (HYDROL)
    """
    import os
    data_dir = os.path.join(os.path.dirname(__file__), "sample_data", "DATA")
    if name == "glen_canyon":
        return {
            "geometry": read_geometry_file(os.path.join(data_dir, "GLENIN")),
            "ws_output": read_ws_output(os.path.join(data_dir, "GLENOUT")),
            "plot": read_plot_file(os.path.join(data_dir, "GLENPLOT")),
            "ecndat": read_ecn_input(
                os.path.join(data_dir, "ECNDAT"),
                os.path.join(data_dir, "GLENECN"),
            ),
            "boundary_layer": read_bl_file(os.path.join(data_dir, "GLENHY")),
        }
    elif name == "blue_mesa":
        return {
            "geometry": read_geometry_file(os.path.join(data_dir, "SPWY")),
        }
    elif name == "hoover":
        return {
            "boundary_layer": read_bl_file(os.path.join(data_dir, "HYDROL")),
        }
    raise ValueError(f"Unknown sample: {name}")


if __name__ == "__main__":
    import sys
    data = load_sample_data("glen_canyon")
    g = data["geometry"]
    o = data["ws_output"]
    print(f"=== Glen Canyon sample data ===")
    print(f"Title: {g.title!r}")
    print(f"Q = {g.q} m^3/s, y0 = {g.y0} m, k_s = {g.k_s}, n_units = {g.n_units}")
    print(f"NSTA = {g.nsta}, stations parsed = {len(g.stations)}")
    print(f"First station: STA={g.stations[0].sta} invert={g.stations[0].invert}")
    print(f"")
    print(f"=== WS output ===")
    print(f"Title: {o.title!r}")
    print(f"Q = {o.q} cms, y0 = {o.y0} m, roughness = {o.roughness_mm} mm, Manning n = {o.manning_n}")
    print(f"EGL at boundary layer start = {o.egl_initial} m")
    print(f"Profile rows: {len(o.profile_rows)}")
    print(f"Cavitation rows: {len(o.cavitation_rows)}")
    if o.profile_rows:
        r = o.profile_rows[0]
        print(f"First profile row: STA {r.sta}, depth {r.depth} m, V = {r.velocity} m/s, profile {r.profile}")
