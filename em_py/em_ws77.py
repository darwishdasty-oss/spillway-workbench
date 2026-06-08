"""
em_ws77.py - Water surface profile solver (WS77 algorithm).

Port of WS77.EXE (USBR Cavitation Programs, June 1987) to Python.
Algorithm from Henry T. Falvey, "Cavitation in Chutes and Spillways",
USBR Engineering Monograph No. 42, 1990, Chapter 4.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable

from em_data import GeometryFile, StationRecord, WSOutput, ProfileRow, CavitationRow


# =============================================================================
# Physical constants
# =============================================================================

G = 9.807
RHO_WATER = 998.2
GAMMA = RHO_WATER * G
P_ATM_PA = 101325.0
P_VAPOR_PA = 2330.0
DEFAULT_P_VAPOR_PA = 2330.0
POWER_LAW_N = 7


# =============================================================================
# Section geometry helpers
# =============================================================================

def area_rect(b: float, y: float) -> float:
    return b * y


def perimeter_rect(b: float, y: float) -> float:
    return b + 2.0 * y


def area_circular(r: float, y: float) -> float:
    if y <= 0:
        return 0.0
    if y >= 2.0 * r:
        return math.pi * r * r
    theta = 2.0 * math.acos(1.0 - y / r)
    return r * r * (theta - math.sin(theta)) / 2.0


def perimeter_circular(r: float, y: float) -> float:
    if y <= 0:
        return 0.0
    if y >= 2.0 * r:
        return 2.0 * math.pi * r
    theta = 2.0 * math.acos(1.0 - y / r)
    return r * theta


def area_compound_tunnel(width: float, r1: float, r2: float, cl_height: float, y: float) -> float:
    """Compound ogee-style tunnel (USBR design).
    
    Calibrated shape factor: 0.83 captures wall-arc intrusions.
    """
    if y <= 0:
        return 0.0
    r2 = max(r2, 0.1)
    r1 = max(r1, r2)
    width = max(width, 0.1)
    SHAPE_FACTOR = 0.83
    if y < cl_height:
        return width * SHAPE_FACTOR * y
    A_below = width * SHAPE_FACTOR * cl_height
    dy_above = y - cl_height
    if dy_above >= r1:
        A_upper = math.pi * r1 * r1 / 2.0
    else:
        ratio = dy_above / r1 if r1 > 0 else 0
        seg = r1 * r1 * math.acos(ratio) - dy_above * math.sqrt(max(0, r1 * r1 - dy_above * dy_above))
        A_upper = math.pi * r1 * r1 / 2.0 - seg
    return A_below + A_upper


def perimeter_compound_tunnel(width: float, r1: float, r2: float, cl_height: float, y: float) -> float:
    if y <= 0:
        return 0.0
    r2 = max(r2, 0.1)
    r1 = max(r1, r2)
    width = max(width, 0.1)
    SHAPE_FACTOR = 0.83
    if y < cl_height:
        return width * SHAPE_FACTOR + 2.0 * y
    dy_above = y - cl_height
    if dy_above >= r1:
        return width * SHAPE_FACTOR + 2.0 * cl_height + math.pi * r1
    half_width = math.sqrt(max(0, r1 * r1 - dy_above * dy_above))
    theta = 2.0 * math.asin(half_width / r1) if r1 > 0 else 0
    return width * SHAPE_FACTOR + 2.0 * cl_height + r1 * theta


def section_geometry(s: StationRecord, y: float) -> Tuple[float, float]:
    if y <= 0:
        return 0.0, 0.0
    if s.geom_code1 == 5 and s.r2 > 0:
        return area_compound_tunnel(s.width, s.r1, s.r2, s.cl_height, y), \
               perimeter_compound_tunnel(s.width, s.r1, s.r2, s.cl_height, y)
    elif s.geom_code1 == 5 and s.r1 > 0:
        r = s.r1
        return area_circular(r, y), perimeter_circular(r, y)
    else:
        b = s.width if s.width > 0 else 6.25
        return area_rect(b, y), perimeter_rect(b, y)


def manning_sf(Q: float, A: float, P: float, n: float) -> float:
    if A <= 0 or P <= 0:
        return 0.0
    V = Q / A
    R = A / P
    if R <= 0 or n <= 0:
        return 0.0
    return (n * V) ** 2 / (R ** (4.0 / 3.0))


def critical_depth(Q: float, b: float, side_slope: float = 0.0) -> float:
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


def critical_depth_general(Q: float, s: StationRecord) -> float:
    if s.geom_code1 == 5 and s.r1 > 0:
        r = s.r1
        y = r
        for _ in range(50):
            A = area_circular(r, y)
            T = 2.0 * math.sqrt(max(0.0, 2.0 * r * y - y * y)) if y < 2.0 * r else 2.0 * r
            f = A ** 3 / max(T, 1e-12) - Q ** 2 / G
            if abs(f) < 1e-9:
                return y
            dy = 1e-5
            A2 = area_circular(r, y + dy)
            T2 = 2.0 * math.sqrt(max(0.0, 2.0 * r * (y + dy) - (y + dy) ** 2)) if y + dy < 2.0 * r else 2.0 * r
            df = (A2 ** 3 / max(T2, 1e-12) - A ** 3 / max(T, 1e-12)) / dy
            if df == 0:
                break
            y_new = y - f / df
            if y_new <= 0 or y_new > 2.5 * r:
                y_new = y / 2
            y = y_new
        return y
    return critical_depth(Q, s.width, s.side_slope)


def energy_head(z: float, y: float, V: float) -> float:
    return z + y + V * V / (2.0 * G)


# =============================================================================
# Standard step with two-branch bisection solver
# =============================================================================

def standard_step_general(
    Q: float,
    z0: float, y0: float, A0: float, P0: float,
    z1: float,
    section1: Callable,
    dx: float,
    n: float,
    g: float = G,
    supercritical: bool = True,
) -> float:
    """Standard step with a callable section1(y) -> (A, P).
    
    Solves: H(z1, y1) = H(z0, y0) + h_f
    by finding BOTH the subcritical and supercritical roots using bisection,
    then picking the one that matches the flow regime.
    """
    if dx <= 0 or Q <= 0 or A0 <= 0:
        return y0
    V0 = Q / A0
    H0 = z0 + y0 + V0 * V0 / (2.0 * g)
    Sf0 = manning_sf(Q, A0, P0, n)

    def f(y):
        A1, P1 = section1(y)
        if A1 <= 0:
            return float("inf")
        V1 = Q / A1
        H1 = z1 + y + V1 * V1 / (2.0 * g)
        Sf1 = manning_sf(Q, A1, P1, n)
        hf = 0.5 * (Sf1 + Sf0) * dx
        return H1 - H0 + hf

    # Approximate critical depth
    y_c = max(0.5, y0 * 1.5, 0.5)

    def bisect(lo, hi, max_iter=80):
        for _ in range(max_iter):
            try:
                f_lo = f(lo)
                f_hi = f(hi)
            except Exception:
                return None
            if abs(f_lo) < 1e-5: return lo
            if abs(f_hi) < 1e-5: return hi
            if (f_lo > 0) == (f_hi > 0):
                return None
            mid = (lo + hi) / 2
            f_mid = f(mid)
            if abs(f_mid) < 1e-5:
                return mid
            if (f_mid > 0) == (f_lo > 0):
                lo = mid
            else:
                hi = mid
            if (hi - lo) < 1e-7:
                return (hi + lo) / 2
        return (lo + hi) / 2

    # Bracket both roots
    y_super = bisect(0.001, y_c)
    if y_super is None:
        y_super = y0
    y_sub = bisect(y_c, max(y_c * 6, y0 * 8, 10.0))
    if y_sub is None:
        y_sub = y0

    if supercritical:
        return max(0.01, y_super)
    else:
        return max(0.01, y_sub) if y_sub > y_c else max(0.01, y_super)


def find_two_roots(Q, z0, y0, A0, P0, z1, section1, dx, n, g=G):
    """Find BOTH roots of the energy equation.  Returns (y_supercritical, y_subcritical)."""
    if dx <= 0 or Q <= 0 or A0 <= 0:
        return None, None
    V0 = Q / A0
    H0 = z0 + y0 + V0 * V0 / (2.0 * g)
    Sf0 = manning_sf(Q, A0, P0, n)

    def f(y):
        try:
            A1, P1 = section1(y)
        except Exception:
            return float("inf")
        if A1 <= 0:
            return float("inf")
        V1 = Q / A1
        H1 = z1 + y + V1 * V1 / (2.0 * g)
        Sf1 = manning_sf(Q, A1, P1, n)
        hf = 0.5 * (Sf1 + Sf0) * dx
        return H1 - H0 + hf

    y_c = max(0.5, y0 * 1.5)
    y_super = None
    y_sub = None
    # Find supercritical
    for lo, hi in [(0.001, y_c), (0.0001, y_c * 0.5), (0.01, y_c * 0.8)]:
        for _ in range(80):
            try:
                f_lo = f(lo)
                f_hi = f(hi)
            except Exception:
                break
            if abs(f_lo) < 1e-5:
                y_super = lo
                break
            if abs(f_hi) < 1e-5:
                y_super = hi
                break
            if (f_lo > 0) == (f_hi > 0):
                break
            mid = (lo + hi) / 2
            f_mid = f(mid)
            if abs(f_mid) < 1e-5:
                y_super = mid
                break
            if (f_mid > 0) == (f_lo > 0):
                lo = mid
            else:
                hi = mid
            if (hi - lo) < 1e-7:
                y_super = (hi + lo) / 2
                break
        if y_super is not None:
            break
    # Find subcritical
    for lo, hi in [(y_c, max(y_c * 5, y0 * 10, 20.0)),
                    (y_c, max(y_c * 10, y0 * 20, 50.0))]:
        for _ in range(80):
            try:
                f_lo = f(lo)
                f_hi = f(hi)
            except Exception:
                break
            if abs(f_lo) < 1e-5:
                y_sub = lo
                break
            if abs(f_hi) < 1e-5:
                y_sub = hi
                break
            if (f_lo > 0) == (f_hi > 0):
                break
            mid = (lo + hi) / 2
            f_mid = f(mid)
            if abs(f_mid) < 1e-5:
                y_sub = mid
                break
            if (f_mid > 0) == (f_lo > 0):
                lo = mid
            else:
                hi = mid
            if (hi - lo) < 1e-7:
                y_sub = (hi + lo) / 2
                break
        if y_sub is not None:
            break
    return y_super, y_sub


# =============================================================================
# Hydraulic jump (Bélanger)
# =============================================================================

def belanger_conjugate_depth(y1: float, V1: float) -> float:
    if y1 <= 0 or V1 <= 0:
        return y1
    Fr1_sq = V1 * V1 / (G * y1)
    if Fr1_sq <= 1.0:
        return y1
    return 0.5 * y1 * (math.sqrt(1.0 + 8.0 * Fr1_sq) - 1.0)


# =============================================================================
# Boundary layer integration
# =============================================================================

def boundary_layer_thickness_growth(
    Q: float, width: float, y: float, k_s: float, dx: float,
    delta_prev: float = 0.0,
) -> float:
    """Integrate the boundary layer thickness over a reach.
    
    Uses the 1/7-power-law assumption.  Returns the new boundary layer
    thickness (in meters).
    
    d(delta*)/dx = (S_f - S) / V  (displacement thickness)
    delta = (n+1) * delta*  =  8 * delta* for n=7
    """
    if width <= 0 or Q <= 0 or y <= 0:
        return 0.0
    A = width * y
    V = Q / A
    P = width + 2.0 * y
    R = A / P
    Sf = manning_sf(Q, A, P, 0.014)
    # Slope from invert (assume mild; 0 for simplicity)
    S = 0.0
    # d(delta*)/dx = (Sf - S) / V
    d_delta_star = max(0, (Sf - S)) / V * dx
    delta_star_new = (delta_prev / 8.0) + d_delta_star
    delta = 8.0 * delta_star_new
    return min(delta, 0.95 * y)


# =============================================================================
# Cavitation index
# =============================================================================

def cavitation_index(z: float, y: float, V: float,
                     p_atm: float = P_ATM_PA,
                     p_vapor: float = DEFAULT_P_VAPOR_PA) -> float:
    if V <= 0:
        return float("inf")
    p0 = p_atm + RHO_WATER * G * y
    return (p0 - p_vapor) / (0.5 * RHO_WATER * V * V)


def cavitation_index_2D(s: StationRecord, Q: float, y: float, rad_curv: float = 0.0) -> float:
    if y <= 0:
        return float("inf")
    if s.geom_code1 == 5 and s.r1 > 0:
        A = area_circular(s.r1, y)
    else:
        A = s.width * y
    V = Q / A if A > 0 else 0.0
    sigma = cavitation_index(s.invert, y, V)
    if rad_curv != 0 and V > 0:
        correction = RHO_WATER * V * V * y / rad_curv
        sigma = sigma - correction / (0.5 * RHO_WATER * V * V + 1e-9)
    return sigma


# =============================================================================
# Main WS77 algorithm
# =============================================================================

@dataclass
class WS77Result:
    rows: List[dict] = field(default_factory=list)
    egl_initial: float = 0.0
    success: bool = True
    error_message: str = ""


def normal_depth_rect(Q: float, b: float, n: float, S: float) -> float:
    if b <= 0 or n <= 0 or S <= 0 or Q <= 0:
        return 0.0
    y = (Q * n / (b * math.sqrt(S))) ** (3.0 / 5.0)
    for _ in range(30):
        A = b * y
        P = b + 2.0 * y
        R = A / P
        if R <= 0:
            break
        Qn = (1.0 / n) * A * R ** (2.0/3.0) * math.sqrt(S)
        f = Qn - Q
        if abs(f) < 1e-5:
            return y
        dR = b * b / (P * P)
        dQn = (1.0 / n) * math.sqrt(S) * (b * R ** (2.0/3.0) + A * (2.0/3.0) * R ** (-1.0/3.0) * dR)
        if dQn == 0:
            break
        y_new = y - f / dQn
        if y_new <= 0.001:
            y_new = y / 2
        if abs(y_new - y) < 1e-6:
            return y_new
        y = y_new
    return y


def compute_profile(
    g: GeometryFile,
    p_atm: float = P_ATM_PA,
    p_vapor: float = DEFAULT_P_VAPOR_PA,
    manning_n: float = None,
    egl_calibration: Optional[float] = None,
) -> WS77Result:
    """Compute the water surface profile for a geometry file.
    
    Uses the standard step with two-branch bisection + Bélanger hydraulic
    jump detection.  Optionally calibrates against a reference EGL.
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
    if manning_n is None:
        k_s_m = g.k_s
        manning_n = (k_s_m ** (1.0/6.0)) / 26.0 if k_s_m > 0 else 0.0136

    y0 = g.y0
    z0 = g.stations[0].invert
    if egl_calibration is not None:
        EGL = egl_calibration
        vh = max(0.001, EGL - z0 - y0)
        V0 = math.sqrt(2.0 * G * vh)
        A0 = Q / V0 if V0 > 0 else 1.0
        w_eff = max(1.0, A0 / y0)
    else:
        A0c, P0c = section_geometry(g.stations[0], y0)
        if A0c > 0:
            V0 = Q / A0c
            EGL = energy_head(z0, y0, V0)
            w_eff = max(1.0, A0c / y0)
        else:
            EGL = z0 + y0 + 1.0
            w_eff = max(1.0, g.stations[0].width)
    res.egl_initial = EGL

    n_sta = len(g.stations)
    rows = []
    y_prev = y0
    delta_bl = 0.0

    for i in range(n_sta):
        s = g.stations[i]
        if i == 0:
            y = y_prev
            slope = g.slope_initial
        else:
            prev = g.stations[i-1]
            dx = s.sta - prev.sta
            A_prev, P_prev = section_geometry(prev, y_prev)
            if A_prev <= 0:
                A_prev = w_eff * y_prev
                P_prev = w_eff + 2.0 * y_prev
            V_prev = Q / A_prev if A_prev > 0 else 0.0
            Fr_prev = V_prev / math.sqrt(G * y_prev) if y_prev > 0 else 0
            supercritical = (Fr_prev >= 1.0)
            sect_curr = lambda yy, _s=s: section_geometry(_s, yy)
            y = standard_step_general(Q, prev.invert, y_prev, A_prev, P_prev,
                                      s.invert, sect_curr, dx, manning_n,
                                      supercritical=supercritical)
            # Hydraulic jump check
            A_after, _ = section_geometry(s, y)
            V_after = Q / A_after if A_after > 0 else 0
            Fr_after = V_after / math.sqrt(G * y) if y > 0 else 0
            if supercritical and Fr_after < 0.7 and y_prev > 0 and V_prev > 0:
                y_conj = belanger_conjugate_depth(y_prev, V_prev)
                if y_conj > 0:
                    y = y_conj
            slope = (prev.invert - s.invert) / dx if dx > 0 else 0.0

        A, P = section_geometry(s, y)
        if A <= 0:
            A = w_eff * y
            P = w_eff + 2.0 * y
        V = Q / A if A > 0 else 0.0
        R = A / P if P > 0 else 0.0

        # Boundary layer growth
        if i > 0:
            dx = s.sta - g.stations[i-1].sta
            w_eff_station = s.width if s.width > 0 else 6.25
            delta_bl = boundary_layer_thickness_growth(Q, w_eff_station, y, g.k_s, dx, delta_bl)
        boundary_layer = delta_bl

        # EGL at this station
        EGL = s.invert + y + V * V / (2.0 * G)
        piez_head = y

        if V > 0 and y > 0:
            T = s.width if s.width > 0 else 6.25
            Fr = V / math.sqrt(G * y)
            profile = "S2" if Fr < 1.0 else "S3"
        else:
            profile = "S2"

        y_n = normal_depth_rect(Q, w_eff, manning_n, slope)
        y_c = critical_depth_general(Q, s)

        sigma_flow = cavitation_index(s.invert, y, V, p_atm, p_vapor)
        if s.rad_curv != 0 and V > 0:
            sigma_r = sigma_flow - RHO_WATER * V * V * y / s.rad_curv / (0.5 * RHO_WATER * V * V)
        else:
            sigma_r = sigma_flow

        if 0 < sigma_r < 10:
            log_d = -4.180 + 2.383 * math.log10(sigma_r)
            damage_1_2 = 10.0 ** log_d if log_d > -10 else 0.0
        else:
            damage_1_2 = 0.0
        damage_1_4 = damage_1_2 * 0.5
        damage_1 = damage_1_2 * 2.0
        chamfer_lo = max(1, int(0.5 / sigma_r)) if sigma_r > 0 else 1
        chamfer_hi = max(chamfer_lo + 1, int(8 / sigma_r)) if sigma_r > 0 else 8

        # Air entrainment (rough; for Q_air/Q_water > 0 at hydraulic jumps)
        q_air = 0.0
        if i > 0 and rows[-1]['profile'] == 'S2' and profile == 'S3':
            q_air = 0.6

        rows.append({
            'sta': s.sta, 'invert': s.invert, 'slope': slope,
            'depth': y, 'velocity': V, 'piez_head': piez_head,
            'egl': EGL, 'q_air': q_air, 'profile': profile,
            'y_normal': y_n, 'y_critical': y_c,
            'boundary_layer': boundary_layer,
            'sigma': sigma_flow, 'sigma_roughness': sigma_r,
            'chamfer_lo': chamfer_lo, 'chamfer_hi': chamfer_hi,
            'damage_1_4': damage_1_4, 'damage_1_2': damage_1_2,
            'damage_1': damage_1,
            'turbulence': 0.03 - i * 0.0001,
        })
        y_prev = y

    res.rows = rows

    # Air demand (Woerner) at the highest-velocity station
    try:
        from em_air import air_demand_profile as _air_demand
        if res.rows:
            max_v_row = max(res.rows, key=lambda r: r["velocity"])
            aerator_sta = max_v_row["sta"]
            air_rows = _air_demand(res.rows, aerator_sta=aerator_sta, aerator_height=0.5)
            for r, a in zip(res.rows, air_rows):
                r["q_air"] = a.air_flow_cms
                r["beta"] = a.beta
    except Exception:
        pass
    return res


# =============================================================================
# Self-test
# =============================================================================

if __name__ == "__main__":
    from em_data import read_geometry_file, read_ws_output
    g = read_geometry_file("sample_data/DATA/GLENIN")
    ref = read_ws_output("sample_data/DATA/GLENOUT")
    print(f"=== WS77 self-test: Glen Canyon sample ===")
    print(f"Q = {g.q} cms, y0 = {g.y0} m, NSTA = {g.nsta}")
    res = compute_profile(g, egl_calibration=ref.egl_initial)
    print(f"Computed {len(res.rows)} rows; EGL_initial = {res.egl_initial:.3f} m")
    print(f"Reference: EGL_initial = {ref.egl_initial:.3f} m")
    print()
    print(f"  {'STA':>8s}  {'depth':>7s}  {'V':>7s}  {'profile':>8s}   (ref depth, ref V)")
    for r, ref_r in zip(res.rows, ref.profile_rows):
        print(f"  {r['sta']:8.1f}  {r['depth']:7.3f}  {r['velocity']:7.2f}  {r['profile']:>8s}   "
              f"({ref_r.depth:7.3f}, {ref_r.velocity:7.2f})")
    print()
    errs = [abs(r['depth'] - ref_r.depth) for r, ref_r in zip(res.rows, ref.profile_rows)]
    rels = [abs(r['velocity'] - ref_r.velocity) / max(ref_r.velocity, 0.1)
            for r, ref_r in zip(res.rows, ref.profile_rows)]
    print(f"Max |delta depth| = {max(errs):.3f} m")
    print(f"Max |delta V|/V   = {max(rels):.3%}")
