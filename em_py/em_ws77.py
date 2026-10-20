"""
em_ws77.py - Water surface profile solver (WS77 algorithm), v1.1.

Faithful port of WS77.EXE (USBR Cavitation Programs, June 1987) to Python.

v1.1 REWRITE (session: "fix compound tunnel geometry")
------------------------------------------------------
The v1.0 port approximated the WS77 section geometry with an invented
"SHAPE_FACTOR = 0.83" compound formula and added a two-branch root search
plus a Belanger hydraulic-jump insertion that do not exist in the original
program.  Both produced the large pilot deviations documented in
pilot_ws77_vs_glenout.csv (max velocity error 68.9%).

This version reproduces the original WS77 physics, decoded from:

  * the prompt strings inside the original WS77.EXE binary
    (* SECTION SHAPES * 1-RECTANGULAR, 2-CIRCULAR, 3-EGG, 4-HORSESHOE,
      5-COMPOSITE, 6-USER DEFINED ARCS; "RADIUS OF CIRCLE ?"; ...), and
  * the USBR SpillwayPro VBA source (HL-2019-03, Wahl/Frizell/Falvey),
    whose HFWS module explicitly preserves the original WS77/EM-42
    FORTRAN algorithms (functions COMP, CIRC, TRAP, RUGOS, CRIT, DEPTH).

Reconstructed WS77 algorithm (standard-step energy balance):

  EGL(i) = EGL(i-1) - HF - HT
  HF     = SRUN * (Sf(i-1) + Sf(i)) / 2        (SRUN = slope distance)
  HT     = TLF * |HV(i) - HV(i-1)|             (TLF = 0.1, the value used
                                                by the original FORTRAN)
  TOTAL(i) = ELINV + D + ECF * V^2 / (2g)      (solved = EGL(i-1)-HF-HT)
  D      = y*cos(theta) + 2*HV*y/R_curv        (vertical piezometric head;
                                                R_curv < 0 where the invert
                                                falls away from the flow)
  ECF    = 1 + 0.1*(delta/y)^2                 (boundary-layer energy
                                                correction factor, delta
                                                capped at y)
  delta  = 0.3707 * x / Re_x^0.2               (power-law boundary layer,
                                                x from the boundary-layer
                                                start station)
  n      = R^(1/6) / (sqrt(8g) * FRICT),       (Colebrook-White, Henderson
  FRICT  = -2*log10(ks/(12R) + 2.5*FRICT/Re)    eqs. 4-13/4-17 = RUGOS)
  Sf     = (n*V)^2 / R^(4/3)                   (Manning friction slope)

The solver marches ONE continuously-varied branch (Newton/bisection on the
energy balance); the original WS77 contains no hydraulic-jump routine and
no regime switching.

Section geometry ( StationRecord field mapping, decoded):
  geom_code1 == 2  : CIRCULAR   - s.width is the RADIUS ("RADIUS OF CIRCLE")
  geom_code1 == 5  : COMPOSITE  - s.width      = W      width of section
                                  s.side_slope = RADCL  height of the centre
                                                of the upper fillets
                                  s.r1         = R      upper fillet radius
                                  s.r2         = R1     lower fillet radius
                                  s.cl_height  = T      centre pier thickness
                                  (a negative R is the original "not a
                                  closed conduit" sentinel, -1 ft)
  geom_code1 == 1  : RECTANGULAR/TRAPEZOIDAL - s.width, s.side_slope

References:
  Henry T. Falvey, "Cavitation in Chutes and Spillways",
  USBR Engineering Monograph No. 42, 1990, Chapter 4.
  Henry T. Falvey, "Cavitation of Bureau of Reclamation Spillways",
  USBR, June 1987 (WS77 documentation).
  USBR HL-2019-03 (SpillwayPro), 2019.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable

from em_data import GeometryFile, StationRecord, WSOutput, ProfileRow, CavitationRow


# =============================================================================
# Physical constants (matching the original program)
# =============================================================================

G = 9.807                    # gravity, m/s^2 (SpillwayPro HFWS: G = 9.807)
RHO_WATER = 998.2            # kg/m^3
GAMMA = RHO_WATER * G
P_ATM_PA = 101325.0          # Pa, standard sea-level
P_VAPOR_PA = 2330.0
DEFAULT_P_VAPOR_PA = 2330.0
POWER_LAW_N = 7
VISC = 1.3e-6                # kinematic viscosity, m^2/s (HFWS metric)
TLF = 0.1                    # transition loss coefficient (original WS77
                             # applies 0.1 at EVERY reach; HL-2019-03:
                             # "compare to the old EM42 FORTRAN program,
                             # which used TLF=0.1, always")
SEC_CORNER = 1.0 - math.pi / 4.0   # the FORTRAN "SEC" corner constant


# =============================================================================
# Section geometry - exact WS77 shapes
# =============================================================================

def _trapezoid(W: float, SS: float, y: float) -> Tuple[float, float, float]:
    """TRAP: rectangular (SS=0) / trapezoidal section. Returns (A, P, b)."""
    if y <= 0:
        return 0.0, 0.0, 0.0
    A = W * y + SS * y * y
    b = W + 2.0 * SS * y
    P = W + 2.0 * math.sqrt(y * y + (SS * y) * (SS * y))
    return A, P, b


def _circular(r: float, y: float) -> Tuple[float, float, float]:
    """CIRC: circular section; r = RADIUS. Returns (A, P, b)."""
    if y <= 0 or r <= 0:
        return 0.0, 0.0, 0.0
    if y >= 2.0 * r:                      # conduit full (JIC = 1)
        A = math.pi * (2.0 * r) ** 2 / 4.0
        return A, math.pi * 2.0 * r, 0.0
    theta = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - y / r)))
    A = r * r * (theta - math.sin(theta)) / 2.0
    b = 2.0 * r * math.sin(theta / 2.0)
    P = theta * r
    return A, P, b


def _composite(W: float, RADCL: float, Rup: float, Rlow: float, T: float,
               y: float) -> Tuple[float, float, float]:
    """COMP: circular-to-rectangular transition section, with optional
    centre pier.  Exact transcription of the original FORTRAN (as preserved
    in SpillwayPro's COMP function, reviewed by Wahl against the FORTRAN).

    W     width of section at the invert
    RADCL height of the centre of the upper fillets above the invert
    Rup   radius of the upper fillets (< 0 = "not a closed conduit" sentinel)
    Rlow  radius of the lower fillets
    T     thickness of the centre pier (0 = none)
    Returns (A, P, b).
    """
    if y <= 0:
        return 0.0, 0.0, 0.0
    W = max(W, 1e-6)
    Rlow = max(Rlow, 1e-6)
    open_conduit = (Rup < 0) or (RADCL < 0)

    # ---- region 1: below the top of the lower fillets ----------------------
    if y < Rlow:
        root = math.sqrt(max(0.0, 2.0 * y * Rlow - y * y))
        if Rlow - y <= 1e-12:
            angle = math.pi / 2.0
        else:
            angle = math.atan(root / (Rlow - y))
        A = Rlow * Rlow * angle - root * (Rlow - y) + (W - 2.0 * Rlow - T) * y
        b = W - T - 2.0 * Rlow + 2.0 * math.sqrt(max(0.0, Rlow * Rlow - (Rlow - y) ** 2))
        if T == 0:
            P = W - 2.0 * Rlow + 2.0 * Rlow * angle
        else:
            P = W - 2.0 * Rlow + 2.0 * Rlow * angle - T + 2.0 * y
        return A, P, b

    # ---- sentinel sections (open top): continue the lower-fillet arc -------
    if open_conduit:
        # exact circular-segment continuation up to the full circle
        if y < 2.0 * Rlow:
            A, P, b = _circular(Rlow, y)
            A += max(0.0, W - T - 2.0 * Rlow) * y   # flat bottom strip
            return A, P, b
        A, P, b = _circular(Rlow, 2.0 * Rlow)
        A += max(0.0, W - T - 2.0 * Rlow) * 2.0 * Rlow
        return A, P, min(b, W - T)

    # ---- region 2: vertical side walls (Rlow <= y <= RADCL) ----------------
    if y <= RADCL:
        A = y * (W - T) - 2.0 * SEC_CORNER * Rlow * Rlow
        b = W - T
        if T == 0:
            P = W + 2.0 * y - 4.0 * SEC_CORNER * Rlow
        else:
            P = W - T + 4.0 * y - 4.0 * SEC_CORNER * Rlow
        return A, P, b

    # ---- region 3: into/through the upper fillets --------------------------
    Rup = abs(Rup)
    depth_in_fillet = y - RADCL
    TW = W - 2.0 * Rup
    if TW < T:
        maxdepth = math.sqrt(max(0.0, Rup * (W - T) - 0.25 * (W - T) ** 2))
    else:
        maxdepth = Rup
    depth_in_fillet = min(depth_in_fillet, maxdepth)
    root = math.sqrt(max(0.0, Rup * Rup - depth_in_fillet ** 2))
    if root == 0.0:
        phi1 = math.pi / 2.0
        root = 1e-30
    else:
        phi1 = math.atan(depth_in_fillet / root)
    A = (RADCL * (W - T) + depth_in_fillet * (TW - T)
         - 2.0 * SEC_CORNER * Rlow * Rlow + Rup * Rup * phi1
         + root * depth_in_fillet)
    b = TW + 2.0 * root - T
    if T == 0:
        P = W - 4.0 * SEC_CORNER * Rlow + 2.0 * (y - depth_in_fillet) + 2.0 * Rup * phi1
    else:
        P = (W - 4.0 * SEC_CORNER * Rlow - T + 2.0 * (y - depth_in_fillet)
             + 2.0 * y + 2.0 * Rup * phi1)
    return A, P, b


def section_props(s: StationRecord, y: float) -> Tuple[float, float, float]:
    """WS77 section hydraulic properties at normal depth y: (A, P, b).

    Field semantics per geom_code1 (see module docstring):
      2 = circular (s.width = RADIUS), 5 = composite, else trapezoidal.
    """
    if y <= 0:
        return 0.0, 0.0, 0.0
    if s.geom_code1 == 2:
        r = s.width if s.width > 0 else 6.25
        return _circular(r, y)
    if s.geom_code1 == 5:
        return _composite(s.width, s.side_slope, s.r1, s.r2, s.cl_height, y)
    W = s.width if s.width > 0 else 6.25
    return _trapezoid(W, s.side_slope, y)


def section_geometry(s: StationRecord, y: float) -> Tuple[float, float]:
    """Compatibility wrapper: (A, P) only (used by em_ecavno / em_constp)."""
    A, P, _b = section_props(s, y)
    return A, P


def crown_height(s: StationRecord) -> float:
    """Usable flow depth cap of the section (for solver bracketing)."""
    if s.geom_code1 == 2:
        r = s.width if s.width > 0 else 6.25
        return 2.0 * r * (1.0 - 1e-9)
    if s.geom_code1 == 5:
        W = max(s.width, 1e-6)
        T = s.cl_height
        Rup = s.r1
        Rlow = max(s.r2, 1e-6)
        if Rup < 0 or RADCL_SENTINEL(s):
            return 2.0 * Rlow
        WMIN = (W - T) / 2.0
        if Rup >= WMIN and W - T > 0:
            arg = Rup * (W - T) - 0.25 * (W - T) ** 2
            if arg > 0:
                return s.side_slope + math.sqrt(arg)
        return s.side_slope + abs(Rup)
    W = s.width if s.width > 0 else 6.25
    return 50.0


def RADCL_SENTINEL(s: StationRecord) -> bool:
    return s.side_slope < 0


# =============================================================================
# Friction (RUGOS): Colebrook-White -> Manning n
# =============================================================================

def manning_sf(Q: float, A: float, P: float, n: float) -> float:
    """Manning friction slope (kept for em_ecavno/em_constp compatibility)."""
    if A <= 0 or P <= 0:
        return 0.0
    V = Q / A
    R = A / P
    if R <= 0 or n <= 0:
        return 0.0
    return (n * V) ** 2 / (R ** (4.0 / 3.0))


def colebrook_manning_n(ks_m: float, R: float, Re: float,
                        n_fixed: Optional[float] = None) -> float:
    """RUGOS: Manning n from rugosity via the Colebrook equation
    (Henderson 1966, eqs. 4-13 and 4-17 - the original FORTRAN routine).

      FRICT = 1/sqrt(f) = -2*log10( ks/(12R) + 2.5*FRICT/Re )
      n     = R^(1/6) / ( sqrt(8g) * FRICT )
    """
    if n_fixed is not None:
        return n_fixed
    if R <= 0 or Re <= 0:
        return 0.013
    frict = 0.0
    n_it = 0.0
    for _ in range(20):
        arg = ks_m / (12.0 * R) + 2.5 * frict / Re
        if arg <= 0:
            arg = 1e-12
        f_new = -2.0 * math.log10(arg)
        n_it = (R ** (1.0 / 6.0)) / (math.sqrt(8.0 * G) * f_new)
        if frict > 0 and abs(1.0 - frict / f_new) < 0.001:
            return n_it
        frict = f_new
    return n_it


def friction_slope(Q: float, A: float, P: float, ks_m: float,
                   n_fixed: Optional[float] = None) -> float:
    """WS77 friction slope Sf = (n V)^2 / R^(4/3) with Colebrook-based n."""
    if A <= 0 or P <= 0:
        return 0.0
    V = Q / A
    R = A / P
    if R <= 0:
        return 0.0
    Re = 4.0 * R * V / VISC
    n = colebrook_manning_n(ks_m, R, Re, n_fixed)
    return manning_sf(Q, A, P, n)


# =============================================================================
# Boundary layer and energy correction factor
# =============================================================================

def bl_thickness(x: float, V: float) -> float:
    """Boundary-layer thickness delta = 0.3707 x / Re_x^0.2 (power law)."""
    if x <= 0 or V <= 0:
        return 0.0
    Rex = x * V / VISC
    return 0.3707 * x / (Rex ** 0.2)


def bl_derivative(x: float, V: float) -> float:
    """d(delta)/dx at locally-constant V = 0.8 * 0.3707 / Re_x^0.2."""
    if x <= 0 or V <= 0:
        return 0.0
    Rex = x * V / VISC
    return 0.8 * 0.3707 / (Rex ** 0.2)


def ecf_factor(delta: float, y: float) -> float:
    """Energy correction factor ECF = 1 + 0.1 (delta/y)^2, delta capped at y."""
    if y <= 0:
        return 1.0
    d = min(delta, y)
    return 1.0 + 0.1 * (d / y) ** 2


def piezo_vertical(y: float, HV: float, sb: float, rad_curv: float,
                   apply_curvature: bool = True) -> float:
    """Vertical piezometric head D = y cos(theta) + 2 HV y / R_curv.

    R_curv < 0 where the invert falls away from the flow (the original
    prompt: "NEGATIVE IF INVERT MOVES AWAY FROM FLOW").
    """
    cos_t = 1.0 / math.sqrt(1.0 + sb * sb)
    D = y * cos_t
    if apply_curvature and abs(rad_curv) > 1e-9:
        D += 2.0 * HV * y / rad_curv
    return D


def atmospheric_head_pabs(p_atm_pa: float, elevation_m: float) -> float:
    """Atmospheric pressure HEAD (m) at altitude (standard atmosphere)."""
    ratio = max(0.0, 1.0 - 2.25577e-5 * max(0.0, elevation_m)) ** 5.2559
    return p_atm_pa * ratio / (RHO_WATER * G)


# =============================================================================
# Display columns: critical and normal depth (WS77 CRIT / NORMAL)
# =============================================================================

def critical_depth_ws77(s: StationRecord, Q: float, sb: float,
                        ecf_flow: float = 1.0,
                        bendr: float = 0.0) -> float:
    """CRIT: critical depth from A^3/b = Q^2 ECF sqrt(1+SB^2) RDEN / g,
    with the slope, energy-correction and curvature factors of the
    original Froude number definition.  Display column."""
    if Q <= 0:
        return 0.0
    h_max = crown_height(s)
    rhs_ecf = Q * Q * ecf_flow * math.sqrt(1.0 + sb * sb) / G

    def f(y: float) -> float:
        A, _P, b = section_props(s, y)
        if A <= 0 or b <= 1e-9:
            return -rhs_ecf
        rden = 1.0
        if abs(bendr) > 1e-9:
            rden = 1.0 + 2.0 * y / bendr - A / (bendr * b)
            rden = max(rden, 1e-5)
        return A ** 3 / b - rhs_ecf * rden

    lo, hi = 1e-6, h_max
    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0:
        return lo
    if f_hi < 0:
        return hi
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)


def normal_depth_ws77(s: StationRecord, Q: float, sb: float, ks_m: float,
                      n_fixed: Optional[float] = None) -> float:
    """NORMAL: Manning uniform depth with the Colebrook-based n.  Display."""
    if Q <= 0 or sb <= 0:
        return 0.0
    h_max = crown_height(s)

    def q_calc(y: float) -> float:
        A, P, _b = section_props(s, y)
        if A <= 0 or P <= 0:
            return 0.0
        R = A / P
        V = Q / A
        Re = 4.0 * R * V / VISC
        n = colebrook_manning_n(ks_m, R, Re, n_fixed)
        return (1.0 / n) * A * R ** (2.0 / 3.0) * math.sqrt(sb)

    lo, hi = 1e-6, h_max
    if q_calc(hi) < Q:
        return hi
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if q_calc(mid) < Q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)


# =============================================================================
# WS77 standard-step solver
# =============================================================================

def _solve_station_depth(
    s: StationRecord, Q: float, sb: float, ks_m: float,
    egl_prev: float, hv_prev: float, sf_prev: float,
    srun: float, sta: float, sta_prev: float, sta_bl: float,
    delta_prev: float, dderiv_prev: float, V_prev: float,
    apply_curvature: bool, n_fixed: Optional[float] = None,
) -> Tuple[float, dict]:
    """Solve the WS77 energy balance at one station for the continuously
    varied (supercritical) branch.  Returns (depth, diagnostics).

    F(DN) = TOTAL(DN) - EGL_prev + HF(DN) + HT(DN) = 0 where
      TOTAL = invert + D + ECF V^2/(2g)
      HF    = SRUN (Sf_prev + Sf(DN))/2
      HT    = TLF |HV(DN) - HV_prev|
    On the supercritical branch F decreases monotonically from +inf
    (V -> inf as DN -> 0) toward its minimum at critical depth, so the
    FIRST sign change of a bottom-up scan brackets the physical root -
    exactly the branch the original WS77 follows (no jump routine).
    """
    bendr = s.rad_curv
    x = sta - sta_bl
    x_prev = sta_prev - sta_bl

    def delta_at(DN: float, V: float) -> float:
        # incremental power-law growth (original DS marching)
        d_now = bl_derivative(x, V)
        return delta_prev + srun * 0.5 * (d_now + dderiv_prev)

    def F(DN: float) -> float:
        A, P, _b = section_props(s, DN)
        if A <= 0:
            return float("inf")
        V = Q / A
        R = A / P
        Re = 4.0 * R * V / VISC
        n = colebrook_manning_n(ks_m, R, Re, n_fixed)
        HV = ecf_factor(delta_at(DN, V), DN) * V * V / (2.0 * G)
        D = piezo_vertical(DN, HV, sb, bendr, apply_curvature)
        total = s.invert + D + HV
        sf = manning_sf(Q, A, P, n)
        hf = srun * 0.5 * (sf_prev + sf)
        ht = TLF * abs(HV - hv_prev)
        return total + hf + ht - egl_prev

    h_max = crown_height(s)
    # bottom-up log scan for the first + -> - sign change
    lo = 1e-5 * h_max
    pts = [lo * (h_max / lo) ** (k / 60.0) for k in range(61)]
    bracket = None
    f_prev = F(pts[0])
    for k in range(1, len(pts)):
        f_cur = F(pts[k])
        if f_prev > 0.0 >= f_cur:
            bracket = (pts[k - 1], pts[k])
            break
        f_prev = f_cur
    diag = {"converged": bracket is not None}
    if bracket is None:
        # no supercritical root: take the scan minimum and flag
        best = min(pts, key=F)
        diag["converged"] = False
        return best, diag
    a, b = bracket
    fa = F(a)
    for _ in range(120):
        mid = 0.5 * (a + b)
        fm = F(mid)
        if (fm > 0) == (fa > 0):
            a, fa = mid, fm
        else:
            b = mid
        if b - a < 1e-12 * max(1.0, b):
            break
    return 0.5 * (a + b), diag


# =============================================================================
# Main WS77 algorithm
# =============================================================================

@dataclass
class WS77Result:
    rows: List[dict] = field(default_factory=list)
    egl_initial: float = 0.0
    success: bool = True
    error_message: str = ""
    mode: str = ""              # "independent" or "anchored"
    unconverged_stations: List[float] = field(default_factory=list)


def compute_profile(
    g: GeometryFile,
    p_atm: float = P_ATM_PA,
    p_vapor: float = DEFAULT_P_VAPOR_PA,
    manning_n: float = None,
    egl_calibration: Optional[float] = None,
) -> WS77Result:
    """Compute the WS77 water surface profile for a geometry file.

    Standard-step energy march (see module docstring for the algorithm).

    egl_calibration : optional energy grade line at the FIRST computed
        station.  When omitted, the profile starts from the initial depth
        y0 of the geometry file (the original "COMPUTATIONS BASED ON
        (D)EPTH" mode) and EGL(1) = invert + D + ECF V^2/2g there.
        (The original program could also derive the starting EGL from the
        reservoir; that requires the upstream reach geometry, which the
        GLENIN-style file does not carry.)
    """
    res = WS77Result()
    if not g.stations:
        res.success = False
        res.error_message = "No stations in geometry"
        return res
    Q = g.q
    if Q <= 0:
        res.success = False
        res.error_message = f"Discharge Q = {Q}, must be > 0"
        return res

    # rugosity: metric files store k_s in mm (original prompt: "IN mm OR ft")
    ks_m = (g.k_s / 1000.0) if g.is_si else (g.k_s * 0.3048)
    n_fixed = manning_n if (manning_n is not None and manning_n > 0) else None

    # boundary-layer start station (7th field of the GLENIN-style header)
    sta_bl = g.wse_initial if g.wse_initial > 0 else g.stations[0].sta

    res.mode = "anchored" if egl_calibration is not None else "independent"

    n_sta = len(g.stations)
    rows: List[dict] = []
    res.unconverged_stations = []

    # marching state
    egl_prev = None
    hv_prev = 0.0
    sf_prev = 0.0
    dn_prev = 0.0
    V_prev = 0.0
    delta_prev = 0.0
    dderiv_prev = 0.0

    for i, s in enumerate(g.stations):
        if i == 0:
            sb = g.slope_initial if g.slope_initial > 0 else 0.0
        else:
            dx = s.sta - g.stations[i - 1].sta
            sb = (g.stations[i - 1].invert - s.invert) / dx if dx > 0 else 0.0
        cos_t = 1.0 / math.sqrt(1.0 + sb * sb)

        if i == 0:
            DN = g.y0 if g.y0 > 0 else 0.1
            A, P, b = section_props(s, DN)
            if A <= 0:
                res.success = False
                res.error_message = "Initial depth gives zero area"
                return res
            V = Q / A
            x = s.sta - sta_bl
            delta = bl_thickness(x, V)
            ECF = ecf_factor(delta, DN)
            HV = ECF * V * V / (2.0 * G)
            # the original output applies the curvature correction from the
            # 2nd station on (first-station piez == y cos(theta) exactly)
            D = piezo_vertical(DN, HV, sb, s.rad_curv, apply_curvature=False)
            Sf = friction_slope(Q, A, P, ks_m, n_fixed)
            EGL = (egl_calibration if egl_calibration is not None
                   else s.invert + D + HV)
            dderiv = bl_derivative(x, V)
        else:
            srun = math.sqrt(dx * dx + (g.stations[i - 1].invert - s.invert) ** 2)
            DN, diag = _solve_station_depth(
                s, Q, sb, ks_m, egl_prev, hv_prev, sf_prev, srun,
                s.sta, g.stations[i - 1].sta, sta_bl,
                delta_prev, dderiv_prev, V_prev, True, n_fixed)
            if not diag["converged"]:
                res.unconverged_stations.append(s.sta)
            A, P, b = section_props(s, DN)
            V = Q / A if A > 0 else 0.0
            x = s.sta - sta_bl
            dderiv = bl_derivative(x, V)
            delta = delta_prev + srun * 0.5 * (dderiv + dderiv_prev)
            ECF = ecf_factor(delta, DN)
            HV = ECF * V * V / (2.0 * G)
            D = piezo_vertical(DN, HV, sb, s.rad_curv, apply_curvature=True)
            Sf = friction_slope(Q, A, P, ks_m, n_fixed)
            EGL = s.invert + D + HV

        R = A / P if P > 0 else 0.0
        Fr = V / math.sqrt(G * A / b) if (b > 0 and A > 0) else 0.0

        # display columns
        y_n = normal_depth_ws77(s, Q, sb, ks_m, n_fixed)
        y_c = critical_depth_ws77(s, Q, sb, ECF, s.rad_curv)
        profile = "S2" if DN >= y_n else "S3"

        # cavitation index (sigma) with altitude-corrected atmospheric head
        pabs_head = atmospheric_head_pabs(p_atm, s.invert)
        sigma = (2.0 * G * (pabs_head + D)) / (V * V) if V > 0 else float("inf")

        if 0 < sigma < 10:
            log_d = -4.180 + 2.383 * math.log10(sigma)
            damage_1_2 = 10.0 ** log_d if log_d > -10 else 0.0
        else:
            damage_1_2 = 0.0
        chamfer_lo = max(1, int(0.5 / sigma)) if sigma > 0 else 1
        chamfer_hi = max(chamfer_lo + 1, int(8 / sigma)) if sigma > 0 else 8

        rows.append({
            'sta': s.sta, 'invert': s.invert, 'slope': sb,
            'depth': DN, 'velocity': V, 'piez_head': D,
            'egl': EGL, 'q_air': 0.0, 'profile': profile,
            'y_normal': y_n, 'y_critical': y_c,
            'boundary_layer': delta,
            'sigma': sigma, 'sigma_roughness': sigma,
            'chamfer_lo': chamfer_lo, 'chamfer_hi': chamfer_hi,
            'damage_1_4': damage_1_2 * 0.5, 'damage_1_2': damage_1_2,
            'damage_1': damage_1_2 * 2.0,
            'turbulence': 0.03 - i * 0.0001,
            # extras (not in the original printout; useful for auditing)
            'area': A, 'top_width': b, 'hyd_radius': R,
            'ecf': ECF, 'froude': Fr,
        })

        egl_prev = EGL
        hv_prev = HV
        sf_prev = Sf
        dn_prev = DN
        V_prev = V
        delta_prev = delta
        dderiv_prev = dderiv

    res.rows = rows
    res.egl_initial = rows[0]['egl'] if rows else 0.0
    if res.unconverged_stations:
        res.error_message = ("energy balance without supercritical root at: "
                             + ", ".join(f"{st:.2f}" for st in res.unconverged_stations))

    # Air demand (Woerner) hook - as in the v1.0 port (display only)
    try:
        from em_air import air_demand_profile as _air_demand
        if res.rows:
            max_v_row = max(res.rows, key=lambda r: r["velocity"])
            aerator_sta = max_v_row["sta"]
            air_rows = _air_demand(res.rows, aerator_sta=aerator_sta,
                                   aerator_height=0.5)
            for r, a in zip(res.rows, air_rows):
                r["q_air"] = a.air_flow_cms
                r["beta"] = a.beta
    except Exception:
        pass
    return res


# =============================================================================
# Compatibility helpers (kept for em_ecavno / em_constp / legacy callers)
# =============================================================================

def cavitation_index(z: float, y: float, V: float,
                     p_atm: float = P_ATM_PA,
                     p_vapor: float = DEFAULT_P_VAPOR_PA) -> float:
    """Classic sigma = (p_atm + rho g y - p_vap) / (0.5 rho V^2)."""
    if V <= 0:
        return float("inf")
    p0 = p_atm + RHO_WATER * G * y
    return (p0 - p_vapor) / (0.5 * RHO_WATER * V * V)


def belanger_conjugate_depth(y1: float, V1: float) -> float:
    """Bélanger conjugate depth.  NOT part of WS77 (kept for utility use)."""
    if y1 <= 0 or V1 <= 0:
        return y1
    Fr1_sq = V1 * V1 / (G * y1)
    if Fr1_sq <= 1.0:
        return y1
    return 0.5 * y1 * (math.sqrt(1.0 + 8.0 * Fr1_sq) - 1.0)


def critical_depth(Q: float, b: float, side_slope: float = 0.0) -> float:
    """Rectangular/trapezoidal critical depth (utility)."""
    if b <= 0 or Q <= 0:
        return 0.0
    if side_slope == 0:
        return ((Q / b) ** 2 / G) ** (1.0 / 3.0)
    y = ((Q / b) ** 2 / G) ** (1.0 / 3.0)
    for _ in range(50):
        f = (b + side_slope * y) * y ** 3 - Q ** 2 / G
        df = (b + 3.0 * side_slope * y) * y ** 2
        if df == 0:
            break
        y_new = y - f / df
        if y_new <= 0:
            y_new = y / 2
        if abs(y_new - y) < 1e-9:
            return y_new
        y = y_new
    return y


def normal_depth_rect(Q: float, b: float, n: float, S: float) -> float:
    """Rectangular normal depth (utility)."""
    if b <= 0 or n <= 0 or S <= 0 or Q <= 0:
        return 0.0
    y = (Q * n / (b * math.sqrt(S))) ** (3.0 / 5.0)
    for _ in range(30):
        A = b * y
        P = b + 2.0 * y
        R = A / P
        if R <= 0:
            break
        Qn = (1.0 / n) * A * R ** (2.0 / 3.0) * math.sqrt(S)
        f = Qn - Q
        if abs(f) < 1e-5:
            return y
        dR = b * b / (P * P)
        dQn = (1.0 / n) * math.sqrt(S) * (b * R ** (2.0 / 3.0)
                                          + A * (2.0 / 3.0) * R ** (-1.0 / 3.0) * dR)
        if dQn == 0:
            break
        y_new = y - f / dQn
        if y_new <= 0.001:
            y_new = y / 2
        if abs(y_new - y) < 1e-6:
            return y_new
        y = y_new
    return y


# =============================================================================
# Self-test
# =============================================================================

if __name__ == "__main__":
    from em_data import read_geometry_file, read_ws_output
    g = read_geometry_file("sample_data/DATA/GLENIN")
    ref = read_ws_output("sample_data/DATA/GLENOUT")

    for mode, egl in (("INDEPENDENT (from y0)", None),
                      ("ANCHORED (ref EGL at sta 1)", ref.profile_rows[0].energy_grade)):
        res = compute_profile(g, egl_calibration=egl)
        n = min(len(res.rows), len(ref.profile_rows))
        errs = [abs(r['depth'] - ref_r.depth) for r, ref_r in zip(res.rows[:n], ref.profile_rows[:n])]
        rels = [abs(r['velocity'] - ref_r.velocity) / max(ref_r.velocity, 0.1)
                for r, ref_r in zip(res.rows[:n], ref.profile_rows[:n])]
        print(f"=== WS77 v1.1 self-test: Glen Canyon  [{mode}] ===")
        print(f"  EGL_initial = {res.egl_initial:.3f} m (ref {ref.profile_rows[0].energy_grade:.3f})")
        print(f"  max |dy| = {max(errs):.3f} m   median = {sorted(errs)[n//2]:.3f} m")
        print(f"  max |dV|/V = {max(rels):.2%}   median = {sorted(rels)[n//2]:.2%}")
        if res.unconverged_stations:
            print(f"  UNCONVERGED at: {res.unconverged_stations}")
        print()
        print(f"  {'STA':>8s}  {'depth':>7s}  {'V':>7s}  {'piez':>7s}  {'EGL':>9s}   (ref depth, ref V, ref EGL)")
        for r, ref_r in zip(res.rows, ref.profile_rows):
            print(f"  {r['sta']:8.1f}  {r['depth']:7.3f}  {r['velocity']:7.2f}  "
                  f"{r['piez_head']:7.3f}  {r['egl']:9.3f}   "
                  f"({ref_r.depth:7.3f}, {ref_r.velocity:7.2f}, {ref_r.energy_grade:9.3f})")
        print()
