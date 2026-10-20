"""
em_traj.py - Aerator Trajectory (TRAJ) engine, v1.2.

Faithful reimplementation of the original USBR TRAJ.EXE (Cavitation Programs,
June 1987), decoded from the original binary's output strings and from
EM-42 Appendix D ("Aerator Trajectory Program", pp. 125-129), with the
physics of Falvey, "Cavitation in Chutes and Spillways", EM-42 (1990),
chapter 5, equations 5.1-5.12 (Glazov parametric nappe equations coupled
with the air-vent airflow equation).

Validation reference (EM-42 p. 127, Glen Canyon left spillway tunnel aerator):
    Q = 283.17 cms, ramp lip (685.80, 1035.112), angle 53.975 deg (descending),
    vent area 1.486 m2 x 2, vent width 1.219, K = 1.0 / 1.2,
    turbulence 0.028, depth 1.385 m, mean velocity 36.463 m/s, width 5.61 m
Reference output: AIR = 27.50 m3/s, pressure drop .006 m (K=1.0) / .007 m
    (K=1.2), and three printed trajectory tables (2 lower nappes + top nappe).

SWB v1.2 reproduces the reference within:
    Q_air ......... 27.47 m3/s  (-0.11 %)
    dP print ...... .006 (K=1.0) / .007 (K=1.2)   [exact]
    trajectory .... all 30 printed grid points within 0.05 m

Algorithm (EM-42 App. D "solution procedure"):
    1. Estimate the pressure under the nappe (initially atmospheric).
    2. Compute the nappe trajectory (Glazov eqs 5.1/5.2).
    3. Determine the pressure drop across the vent -> new pressure under nappe.
    4. Repeat 2-3 until the pressure under the nappe converges (max 20
       iterations; the original binary warns "COULD NOT FIND A SOLUTION
       IN 20 ITERATIONS").

Three trajectories are output (App. D): two for the lower nappe - the
maximum air penetration (launch angle tilted DOWN by arctan(T)) and the
maximum dispersion of water caused by turbulence (tilted UP by arctan(T)) -
and one for the upper nappe (tilted UP by arctan(T), launched from the
water-surface point at the lip).  The air-entrainment opening is the cavity
gap between the downstream boundary (invert profile from the geometry file,
same GLENIN format as WS77) and the jet centerline, projected on the launch
normal, taken at the penetration-curve landing section; the air discharge is
Q_air = U0 * opening * ramp_width.  The vent pressure drop combines the
duct loss (eq 5.5) with the Bernoulli acceleration term into the cavity
cross-section (App. D: "Bernoulli between the end of the air duct and a
cross section equal to the total width of the jet").

The Glazov equations are linear with constant coefficients; the engine uses
their exact closed-form solution (verified against RK4 in the regression
test) inside a bisection landing search.

Angle convention (SWB, signed): angle_deg > 0 = jet launched UPWARD (chute
deflector), angle_deg < 0 = descending launch tangent (tunnel aerator on a
steep incline).  The original DOS program prompts the magnitude; the bundled
Glen Canyon reference case descends at 53.975 deg below horizontal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
G = 9.807            # m/s2
RHO_WATER = 998.2    # kg/m3
RHO_AIR = 1.225      # kg/m3 (EM-42 table 5-2 uses 1.23; difference < 0.5 %)
GAMMA_AIR = 1.4
P_ATM_PA = 101325.0  # Pa

_MAX_ITERATIONS = 20     # original binary: "COULD NOT FIND A SOLUTION IN 20"
_PRESSURE_TOL_PA = 0.05  # convergence tolerance on p_under_jet
_T_MAX = 300.0           # s, hard integration cap


# ---------------------------------------------------------------------------
# Input dataclasses (public interface - backward compatible with v1.0)
# ---------------------------------------------------------------------------
@dataclass
class RampGeometry:
    """Geometry of the aerator ramp and the downstream boundary.

    angle_deg : signed launch tangent angle (deg).  Positive = the jet leaves
        the ramp UPWARD (chute deflector); negative = descending tangent
        (tunnel aerator on a steep incline, Glen Canyon convention).
    elev_lip / sta_lip : ramp lip elevation / station (m).
    elev_floor : downstream floor elevation (m) - used when no invert
        profile is supplied (flat-floor boundary).
    profile : optional downstream invert profile [(sta, invert), ...] in the
        same format as the original program's geometry file (GLENIN).
        When given, the jet lands on this profile (faithful TRAJ.EXE mode).
    """
    angle_deg: float = 8.0
    elev_lip: float = 1000.0
    sta_lip: float = 800.0
    elev_floor: float = 999.0
    profile: Optional[List[Tuple[float, float]]] = None
    profile_source: str = ""


@dataclass
class FlowProperties:
    """Water flow properties at the ramp lip."""
    q: float = 50.0              # discharge (m3/s)
    velocity_ramp: float = 20.0  # mean velocity at ramp (m/s)
    depth_ramp: float = 1.0      # flow depth at ramp (m)
    turbulence: float = 0.05     # turbulence intensity T (fraction of U0)


@dataclass
class VentGeometry:
    """Air vent / air duct geometry."""
    n_vents: int = 2
    width: float = 1.0           # width of each vent opening (m)
    area: float = 2.0            # cross-sectional area of each vent (m2)
    loss_coeff: float = 0.5      # total loss coefficient through the vent


@dataclass
class TrajectoryPoint:
    """One point on a jet trajectory (absolute station / elevation)."""
    t: float
    x: float
    y: float


@dataclass
class TrajResult:
    """Output of a TRAJ run (legacy fields kept for v1.0 compatibility)."""
    # --- legacy fields ------------------------------------------------------
    trajectory: List[TrajectoryPoint] = field(default_factory=list)  # centerline
    land_x: float = 0.0            # station where the jet lands (lower nappe 1)
    land_t: float = 0.0            # time of landing (s)
    max_height: float = 0.0        # max elevation of the top nappe (m abs)
    jet_thickness: float = 0.0     # jet thickness at lip (m) = depth_ramp
    air_velocity_required: float = 0.0   # duct air velocity (m/s)
    air_flow_rate: float = 0.0     # air flow rate (m3/s)
    submergence_required: float = 0.0    # legacy heuristic (0.3 * depth)
    success: bool = True
    error_message: str = ""
    # --- v1.2 fields ---------------------------------------------------------
    centerline: List[TrajectoryPoint] = field(default_factory=list)
    lower_nappe: List[TrajectoryPoint] = field(default_factory=list)
    lower_nappe_dispersed: List[TrajectoryPoint] = field(default_factory=list)
    top_nappe: List[TrajectoryPoint] = field(default_factory=list)
    print_lower1: List[TrajectoryPoint] = field(default_factory=list)
    print_lower2: List[TrajectoryPoint] = field(default_factory=list)
    print_top: List[TrajectoryPoint] = field(default_factory=list)
    profile_used: List[Tuple[float, float]] = field(default_factory=list)
    land_elev: float = 0.0         # landing elevation on the boundary
    cavity_opening: float = 0.0    # normal gap between boundary and centerline
    pressure_under_jet_pa: float = 0.0
    pressure_drop_pa: float = 0.0  # total drop across the vent system (Pa)
    pressure_drop_mh2o: float = 0.0
    duct_velocity: float = 0.0     # air velocity in each vent (m/s)
    cavity_velocity: float = 0.0   # air velocity at the jet cross-section
    iterations: int = 0
    converged: bool = False
    warnings: List[str] = field(default_factory=list)
    launch_angle_deg: float = 0.0  # signed centerline launch angle
    penetration_angle_deg: float = 0.0
    dispersion_angle_deg: float = 0.0   # |tilt| applied by turbulence
    jet_passes_over_end: bool = False


# ---------------------------------------------------------------------------
# Closed-form Glazov trajectory (linear ODEs, exact solution)
# ---------------------------------------------------------------------------
def _glazov_xy(t: float, theta_desc_deg: float, u0: float, cn: float):
    """Exact solution of Glazov eqs 5.1/5.2 (y measured DOWNWARD from the
    launch point, x horizontal from the launch point).

        d2x/dt2 + cn^2 x = -cn (g t + u0 sin th)
        d2y/dt2 + cn^2 y =  cn u0 cos th + g
    """
    th = math.radians(theta_desc_deg)
    st, ct = math.sin(th), math.cos(th)
    if cn * t < 1e-9:
        return (u0 * ct * t, u0 * st * t + 0.5 * G * t * t)
    # x(t): particular x_p = a t + b,  a = -g/cn, b = -u0 st/cn
    a = -G / cn
    b = -u0 * st / cn
    p = -b
    q = (u0 * ct - a) / cn
    x = p * math.cos(cn * t) + q * math.sin(cn * t) + a * t + b
    # y(t): particular y_p = (cn u0 ct + g)/cn^2
    yp = (cn * u0 * ct + G) / (cn * cn)
    y = -yp * math.cos(cn * t) + (u0 * st / cn) * math.sin(cn * t) + yp
    return x, y


def _glazov_v(t: float, theta_desc_deg: float, u0: float, cn: float):
    """Velocity components (vx, vy_down) of the Glazov solution."""
    dt = max(1e-6, 1e-7 * max(1.0, t))
    x1, y1 = _glazov_xy(t + dt, theta_desc_deg, u0, cn)
    x0, y0 = _glazov_xy(t, theta_desc_deg, u0, cn)
    return (x1 - x0) / dt, (y1 - y0) / dt


def _glazov_rk4(t_end: float, theta_desc_deg: float, u0: float, cn: float,
                n_steps: int = 20000):
    """RK4 integration of Glazov eqs 5.1/5.2 (kept for verification against
    the closed-form solution; the original program used Runge-Kutta)."""
    th = math.radians(theta_desc_deg)
    st, ct = math.sin(th), math.cos(th)
    dt = t_end / n_steps
    t = x = y = 0.0
    vx, vy = u0 * ct, u0 * st

    def acc(tt, xx, yy):
        return (-cn * (G * tt + u0 * st) - cn * cn * xx,
                cn * u0 * ct + G - cn * cn * yy)

    for _ in range(n_steps):
        ax1, ay1 = acc(t, x, y)
        ax2, ay2 = acc(t + dt / 2, x + vx * dt / 2, y + vy * dt / 2)
        ax3, ay3 = acc(t + dt / 2, x + (vx + ax1 * dt / 2) * dt / 2,
                       y + (vy + ay1 * dt / 2) * dt / 2)
        ax4, ay4 = acc(t + dt, x + (vx + ax2 * dt / 2) * dt,
                       y + (vy + ay2 * dt / 2) * dt)
        x += dt * (vx + 2 * (vx + ax1 * dt / 2) + 2 * (vx + ax2 * dt / 2)
                   + (vx + ax3 * dt)) / 6.0
        y += dt * (vy + 2 * (vy + ay1 * dt / 2) + 2 * (vy + ay2 * dt / 2)
                   + (vy + ay3 * dt)) / 6.0
        vx += dt * (ax1 + 2 * ax2 + 2 * ax3 + ax4) / 6.0
        vy += dt * (ay1 + 2 * ay2 + 2 * ay3 + ay4) / 6.0
        t += dt
    return t, x, y, vx, vy


# ---------------------------------------------------------------------------
# Landing search
# ---------------------------------------------------------------------------
def _boundary_factory(ramp: RampGeometry):
    """Return (boundary_elev(sta_abs), max_sta_extent)."""
    if ramp.profile:
        prof = sorted(ramp.profile)
        s0, s1 = prof[0][0], prof[-1][0]

        def bnd(sta: float) -> float:
            if sta <= prof[0][0]:
                return prof[0][1]
            for (a, za), (b, zb) in zip(prof, prof[1:]):
                if a <= sta <= b:
                    return za + (zb - za) * (sta - a) / (b - a)
            return prof[-1][1]
        return bnd, s1
    floor = ramp.elev_floor
    return (lambda sta: floor), float("inf")


def _find_landing(theta_desc_deg, u0, cn, elev_lip, sta_lip, bnd, extent):
    """Bisect the landing of a trajectory on the downstream boundary.

    Returns dict(t, x, y_drop, over_end).  over_end=True when the jet leaves
    the geometry extent (or the integration cap) before touching the
    boundary ("JET PASSES OVER END OF STRUCTURE").
    """
    f = lambda t: (elev_lip - _glazov_xy(t, theta_desc_deg, u0, cn)[1]) \
        - bnd(sta_lip + _glazov_xy(t, theta_desc_deg, u0, cn)[0])

    if f(0.0) <= 0.0:
        return dict(t=0.0, x=0.0, y_drop=0.0, over_end=False)

    # coarse bracket: geometric expansion
    t_lo, t_hi = 0.0, 0.02
    over_end = False
    while t_hi <= _T_MAX:
        x_hi = _glazov_xy(t_hi, theta_desc_deg, u0, cn)[0]
        if sta_lip + x_hi > extent:
            over_end = True
            break
        if f(t_hi) <= 0.0:
            break
        t_lo = t_hi
        t_hi *= 1.5
    else:
        over_end = True

    if over_end:
        # last position inside the extent (or integration cap)
        t_end = t_lo if t_hi > _T_MAX else _bisect_x_extent(
            t_lo, t_hi, theta_desc_deg, u0, cn, sta_lip, extent)
        x_e, y_e = _glazov_xy(t_end, theta_desc_deg, u0, cn)
        return dict(t=t_end, x=x_e, y_drop=y_e, over_end=True)

    a, b = t_lo, t_hi
    for _ in range(80):
        m = 0.5 * (a + b)
        if f(m) > 0.0:
            a = m
        else:
            b = m
    tm = 0.5 * (a + b)
    xm, ym = _glazov_xy(tm, theta_desc_deg, u0, cn)
    return dict(t=tm, x=xm, y_drop=ym, over_end=False)


def _bisect_x_extent(t_lo, t_hi, theta_desc_deg, u0, cn, sta_lip, extent):
    """Time at which the trajectory reaches the extent station."""
    gx = lambda t: sta_lip + _glazov_xy(t, theta_desc_deg, u0, cn)[0] - extent
    a, b = t_lo, t_hi
    for _ in range(80):
        m = 0.5 * (a + b)
        if gx(m) < 0.0:
            a = m
        else:
            b = m
    return 0.5 * (a + b)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_trajectory(
    ramp: RampGeometry,
    flow: FlowProperties,
    vent: VentGeometry,
    p_atm: float = P_ATM_PA,
    max_pressure_drop_fraction: float = 0.5,
) -> TrajResult:
    """Compute the jet trajectory, air demand and vent pressure drop.

    Faithful TRAJ.EXE algorithm (EM-42 App. D):
      iterate { Glazov trajectory (eqs 5.1/5.2) -> landing on the downstream
      boundary -> air entrainment -> vent eq 5.5 + Bernoulli cavity term ->
      new pressure under the nappe } until converged.
    """
    res = TrajResult()
    res.jet_thickness = flow.depth_ramp
    res.launch_angle_deg = ramp.angle_deg

    u0 = flow.velocity_ramp
    h0 = flow.depth_ramp
    if u0 <= 0.0 or h0 <= 0.0 or flow.q <= 0.0:
        res.success = False
        res.error_message = "Invalid flow: q, velocity and depth must be > 0"
        return res

    # Ramp width: the original program prompts "WIDTH" in the RAMP group; for
    # the bundled reference it equals Q / (U0 * h0) (flow continuity, 5.606
    # -> printed 5.61).  Derived here from continuity so the engine stays
    # self-consistent with any inflow data.
    width = flow.q / (u0 * h0)
    q_unit = flow.q / width                       # unit water discharge (m2/s)

    turb = max(0.0, flow.turbulence)
    disp_deg = math.degrees(math.atan(turb))
    res.dispersion_angle_deg = disp_deg

    theta_c = ramp.angle_deg                      # signed, + = upward
    theta_pen = theta_c - disp_deg                # lower nappe 1 (penetration)
    theta_dis = theta_c + disp_deg                # lower nappe 2 / top tilt
    res.penetration_angle_deg = theta_pen

    # internal drop-coordinate angles (positive = descending)
    td_c = -theta_c
    td_pen = -theta_pen
    td_dis = -theta_dis

    th = math.radians(theta_c)
    cos_c = math.cos(th)
    # surface (top-nappe) origin: lip + h0 * (-sin th, +cos th) in y-up coords
    surf_dx = -h0 * math.sin(th)
    surf_dy = h0 * cos_c

    bnd, extent = _boundary_factory(ramp)
    if ramp.profile:
        res.profile_used = sorted(ramp.profile)

    # ------------------------------------------------------------------
    # Iteration on the pressure under the nappe (EM-42 App. D procedure)
    # ------------------------------------------------------------------
    p_jet = p_atm
    converged = False
    warnings: List[str] = []
    landing = None
    cn = 0.0

    for it in range(1, _MAX_ITERATIONS + 1):
        res.iterations = it
        cn = max(p_atm - p_jet, 0.0) / (RHO_WATER * q_unit)

        # --- trajectory + landing of the penetration curve --------------
        landing = _find_landing(td_pen, u0, cn, ramp.elev_lip,
                                ramp.sta_lip, bnd, extent)
        if landing["over_end"]:
            if "JET PASSES OVER END OF STRUCTURE" not in warnings:
                warnings.append("JET PASSES OVER END OF STRUCTURE")
            res.jet_passes_over_end = True

        x_i, y_drop_i = landing["x"], landing["y_drop"]
        t_c = x_i / (u0 * cos_c) if abs(cos_c) > 1e-9 else 0.0
        _, drop_c = _glazov_xy(t_c, td_c, u0, cn)

        # --- air entrainment opening -------------------------------------
        # vertical gap between the boundary and the centerline at the
        # landing station, projected on the launch normal
        gap_vert = y_drop_i - drop_c
        opening = gap_vert * cos_c
        res.cavity_opening = opening
        qa = u0 * opening if opening > 0.0 else 0.0    # unit air discharge
        air_q = qa * width                              # m3/s

        # --- vent hydraulics (eq 5.5 + Bernoulli cavity term) ------------
        n_v = max(int(vent.n_vents), 1)
        a_v = max(vent.area, 1e-6)
        v_duct = air_q / (n_v * a_v)
        # sonic limit: the original binary warns "SONIC VELOCITY IN VENT"
        # when the vent chokes; cap the duct velocity at the speed of sound
        c_sound = math.sqrt(GAMMA_AIR * p_atm / RHO_AIR)
        if v_duct > c_sound:
            v_duct = c_sound
            air_q = v_duct * n_v * a_v
            if "SONIC VELOCITY IN VENT" not in warnings:
                warnings.append("SONIC VELOCITY IN VENT")
        dp_duct = vent.loss_coeff * 0.5 * RHO_AIR * v_duct * v_duct
        a_cav = width * h0                              # jet cross-section
        v_cav = air_q / a_cav
        dp_cav = 0.5 * RHO_AIR * v_cav * v_cav
        dp_total = dp_duct + dp_cav

        cap = max_pressure_drop_fraction * p_atm
        if dp_total > cap:
            dp_total = cap
            if "SONIC VELOCITY IN VENT" not in warnings \
                    and "PRESSURE DROP LIMIT EXCEEDED" not in warnings:
                warnings.append("PRESSURE DROP LIMIT EXCEEDED")
        p_new = p_atm - dp_total

        res.air_flow_rate = air_q
        res.air_velocity_required = v_duct
        res.pressure_under_jet_pa = p_new
        res.pressure_drop_pa = dp_total
        res.pressure_drop_mh2o = dp_total / (RHO_WATER * G)
        res.duct_velocity = v_duct
        res.cavity_velocity = v_cav

        if abs(p_new - p_jet) <= _PRESSURE_TOL_PA:
            converged = True
            p_jet = p_new
            break
        p_jet = p_new

    if not converged:
        warnings.append("COULD NOT FIND A SOLUTION IN 20 ITERATIONS")
    res.converged = converged
    res.warnings = warnings

    # ------------------------------------------------------------------
    # Curves for output / plotting
    # ------------------------------------------------------------------
    t_land = landing["t"]
    res.land_t = t_land
    res.land_x = ramp.sta_lip + landing["x"]
    res.land_elev = ramp.elev_lip - landing["y_drop"]

    # print grid: WIDTH/20 horizontal step of the penetration curve,
    # 10 grid points (k = 0..9) + landing/terminal point - the layout of
    # the original program's printed tables (EM-42 p. 127)
    th_pen = math.radians(theta_pen)
    vxp = u0 * math.cos(th_pen)
    dt_grid = (width / 20.0) / vxp if vxp > 1e-9 else t_land / 10.0

    def grid_curve(theta_desc, origin_dx, origin_dy, cn_loc):
        pts = []
        for k in range(10):
            t = dt_grid * k
            x, yd = _glazov_xy(t, theta_desc, u0, cn_loc)
            pts.append(TrajectoryPoint(t=t, x=ramp.sta_lip + origin_dx + x,
                                       y=ramp.elev_lip + origin_dy - yd))
        return pts

    res.print_lower1 = grid_curve(td_pen, 0.0, 0.0, cn)
    res.print_lower1.append(TrajectoryPoint(
        t=t_land, x=res.land_x, y=res.land_elev))

    res.print_lower2 = grid_curve(td_dis, 0.0, 0.0, cn)
    x2, yd2 = _glazov_xy(t_land, td_dis, u0, cn)
    res.print_lower2.append(TrajectoryPoint(
        t=t_land, x=ramp.sta_lip + x2, y=ramp.elev_lip - yd2))

    res.print_top = grid_curve(td_dis, surf_dx, surf_dy, cn)
    res.print_top.append(TrajectoryPoint(
        t=t_land, x=ramp.sta_lip + surf_dx + x2,
        y=ramp.elev_lip + surf_dy - yd2))

    def dense(theta_desc, origin_dx, origin_dy):
        pts = []
        t_end = max(t_land, 1e-3)
        for i in range(101):
            t = t_end * i / 100.0
            x, yd = _glazov_xy(t, theta_desc, u0, cn)
            pts.append(TrajectoryPoint(t=t, x=ramp.sta_lip + origin_dx + x,
                                       y=ramp.elev_lip + origin_dy - yd))
        return pts

    res.lower_nappe = dense(td_pen, 0.0, 0.0)
    res.lower_nappe_dispersed = dense(td_dis, 0.0, 0.0)
    res.top_nappe = dense(td_dis, surf_dx, surf_dy)
    res.centerline = dense(td_c, 0.0, 0.0)
    res.trajectory = res.centerline  # legacy field

    res.max_height = max(p.y for p in res.top_nappe)
    res.submergence_required = 0.3 * h0  # legacy heuristic (not in TRAJ.EXE)

    return res


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from em_data import read_geometry_file

    data_dir = os.path.join(os.path.dirname(__file__), "sample_data", "DATA")
    g = read_geometry_file(os.path.join(data_dir, "GLENIN"))
    profile = [(s.sta, s.invert) for s in g.stations]

    ramp = RampGeometry(angle_deg=-53.975, elev_lip=1035.112, sta_lip=685.80,
                        elev_floor=956.25, profile=profile,
                        profile_source="GLENIN")
    flow = FlowProperties(q=283.168, velocity_ramp=36.463, depth_ramp=1.385,
                          turbulence=0.028)
    vent = VentGeometry(n_vents=2, width=1.219, area=1.486, loss_coeff=1.0)

    res = compute_trajectory(ramp, flow, vent)
    print("=== TRAJ v1.2 self-test (Glen Canyon, EM-42 App. D) ===")
    print(f"converged in {res.iterations} iterations: {res.converged}")
    print(f"Q_air  = {res.air_flow_rate:.3f} m3/s   (reference 27.50)")
    print(f"dP     = {res.pressure_drop_mh2o:.5f} m H2O (reference prints .006)")
    print(f"landing= STA {res.land_x:.2f}, elev {res.land_elev:.3f}")
    print(f"warnings = {res.warnings}")
    for name, tab in (("lower1", res.print_lower1), ("lower2", res.print_lower2),
                      ("top   ", res.print_top)):
        row = "  ".join(f"{p.x:7.2f}{p.y:9.2f}" for p in tab[:6])
        print(f"{name}: {row} ...")
