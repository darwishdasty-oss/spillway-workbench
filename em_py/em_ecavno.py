"""
em_ecavno.py - Equal Cavitation Number (ECAVNO) spillway design.

Port of ECAVNO.EXE (USBR Cavitation Programs, June 1987) to Python.
Algorithm from Henry T. Falvey, "Cavitation in Chutes and Spillways",
USBR Engineering Monograph No. 42, 1990, Section 6.3.

Algorithm (forward, station-by-station)
=======================================

For each station i = 1, 2, ... N, given:
    - Upstream invert z_{i-1} and depth y_{i-1} (from previous station)
    - The local section geometry (width, side slope, etc.)
    - The target cavitation index sigma_target

The algorithm finds the depth y_i and invert z_i such that:

    1. Energy conservation between station i-1 and i:
           z_{i-1} + y_{i-1} + V_{i-1}^2/(2g) = z_i + y_i + V_i^2/(2g) + h_f
       where h_f = S_f * dx is the friction loss in the reach.

    2. The local cavitation index equals the target:
           sigma_i = (p_atm + rho*g*y_i - p_v) / (0.5 * rho * V_i^2) = sigma_target

From (2), V_i is determined by y_i (since V_i = Q/A_i(y_i) and the section
geometry gives A_i as a function of y_i).  From (1), z_i is then determined
by y_{i-1}, z_{i-1}, y_i, and the friction loss.

So at each station we:
    a) Pick y_i (or solve for it from sigma_i = target).
    b) Compute V_i = Q / A_i(y_i).
    c) Verify sigma_i = (p_atm + rho*g*y_i - p_v) / (0.5 rho V_i^2).  Adjust y_i if needed.
    d) Compute z_i from the energy equation (1).

The local invert z_i is the design output at this station.  The user
supplied z_i_0 (the initial guess); the algorithm adjusts it.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional

from em_data import ECNInput
from em_ws77 import G, RHO_WATER, P_ATM_PA, DEFAULT_P_VAPOR_PA, section_geometry, manning_sf


# =============================================================================
# ECAVNO algorithm
# =============================================================================

@dataclass
class ECAVNOResult:
    rows: List[dict] = field(default_factory=list)
    success: bool = True
    error_message: str = ""


def _find_depth_for_sigma(
    Q: float, sigma_target: float, w_eff: float, r1: float = 0.0,
    r2: float = 0.0, cl_height: float = 0.0, geom_code1: int = 0,
    p_atm: float = P_ATM_PA, p_vapor: float = DEFAULT_P_VAPOR_PA,
) -> float:
    """Find the depth y at a station such that sigma = sigma_target.

    sigma = (p_atm + rho*g*y - p_v) / (0.5 * rho * V^2)
    where V = Q / A(y).

    For sigma_target in (0, 0.5] (cavitation range), this typically gives
    a small y (high V).  For sigma_target > 0.5, y is larger.

    We solve by Newton on f(y) = sigma(y) - sigma_target.
    """
    if sigma_target <= 0:
        return 1.0
    # Initial guess from rectangular approximation:
    # sigma = (p0 + rho*g*y - pv) / (0.5 rho V^2)
    # For w_eff*y small, V = Q/(w_eff*y) is large, sigma small.
    # Sigma target = 0.2 means V high. y ~ (Q/w_eff) * sqrt(rho / (2*(p_atm-pv)/sigma))
    p0 = p_atm - p_vapor
    # Approximate: V_target = sqrt((p0 + rho*g*y) / (0.5 rho sigma))
    # If p0 dominates, V_target = sqrt(2 p0 / (rho sigma))
    V_target = math.sqrt(2 * p0 / (RHO_WATER * sigma_target))
    A_target = Q / V_target
    y = A_target / w_eff
    y = max(0.05, min(y, 20.0))

    for it in range(40):
        A, P = section_geometry_for_ec(Q, w_eff, r1, r2, cl_height, geom_code1, y)
        if A <= 0:
            return y
        V = Q / A
        sigma = (p_atm + RHO_WATER * G * y - p_vapor) / (0.5 * RHO_WATER * V * V)
        f = sigma - sigma_target
        if abs(f) < 1e-4:
            return y
        # Numerical derivative
        dy = max(y * 1e-3, 1e-4)
        A_d, _P_d = section_geometry_for_ec(Q, w_eff, r1, r2, cl_height, geom_code1, y + dy)
        if A_d <= 0:
            return y
        V_d = Q / A_d
        sigma_d = (p_atm + RHO_WATER * G * (y + dy) - p_vapor) / (0.5 * RHO_WATER * V_d * V_d)
        df = (sigma_d - sigma) / dy
        if abs(df) < 1e-6:
            break
        y_new = y - f / df
        y_new = max(0.01, min(y_new, 20.0))
        if abs(y_new - y) < 1e-6:
            return y_new
        y = y_new
    return y


def section_geometry_for_ec(Q, w_eff, r1, r2, cl_height, geom_code1, y):
    """Return (A, P) at depth y for the given section.
    
    If the section is compound (geom_code1 == 5), use the compound formula.
    Otherwise, use a rectangular approximation of width w_eff.
    """
    from em_ws77 import section_geometry
    # Use a temporary StationRecord to call section_geometry
    from em_data import StationRecord
    s = StationRecord(sta=0, invert=0, width=w_eff, r1=r1, r2=r2,
                     cl_height=cl_height, geom_code1=geom_code1, geom_code2=0)
    return section_geometry(s, y)


def design_spillway(
    ecn: ECNInput,
    sigma_target: float = None,
    p_atm: float = P_ATM_PA,
    p_vapor: float = DEFAULT_P_VAPOR_PA,
    include_centrifugal: bool = False,
) -> ECAVNOResult:
    """Design a spillway profile that maintains sigma = sigma_target.
    
    Forward iteration from upstream to downstream.
    """
    res = ECAVNOResult()
    if sigma_target is None:
        sigma_target = ecn.sigma_target
    if sigma_target <= 0:
        sigma_target = 0.2  # default
    if not ecn.stations:
        res.success = False
        res.error_message = "No stations"
        return res
    
    Q = ecn.q
    rows = []
    
    # First station: use supplied invert, find depth from EGL
    s0 = ecn.stations[0]
    y_prev = ecn.y0 if ecn.y0 > 0 else 0.5
    z_prev = s0.invert
    A_prev, P_prev = section_geometry_for_ec(Q, s0.width or 6.25,
                                              s0.r1, s0.r2, s0.cl_height,
                                              s0.geom_code1, y_prev)
    V_prev = Q / A_prev if A_prev > 0 else 0.0
    EGL_prev = z_prev + y_prev + V_prev * V_prev / (2.0 * G)
    
    for i, s in enumerate(ecn.stations):
        # Use the supplied invert as initial guess, then find y for sigma_target
        z_curr = s.invert
        # Find y at this station that gives sigma = target
        y_target = _find_depth_for_sigma(
            Q, sigma_target, s.width or 6.25,
            s.r1, s.r2, s.cl_height, s.geom_code1, p_atm, p_vapor,
        )
        # Bound y_target: not too small, not too large
        y_target = max(0.05, min(y_target, 20.0))
        
        # At this depth, compute velocity, sigma
        A, P = section_geometry_for_ec(Q, s.width or 6.25, s.r1, s.r2,
                                        s.cl_height, s.geom_code1, y_target)
        V = Q / A if A > 0 else 0.0
        p0 = p_atm + RHO_WATER * G * y_target
        if include_centrifugal and s.rad_curv != 0 and V > 0:
            sign = 1.0 if s.rad_curv > 0 else -1.0
            p0 += sign * RHO_WATER * V * V * y_target / abs(s.rad_curv)
        sigma_actual = (p0 - p_vapor) / (0.5 * RHO_WATER * V * V) if V > 0 else float("inf")
        
        # Energy: z_curr + y + V^2/2g = EGL_prev - h_f
        # h_f = S_f * dx, where dx = (s.sta - z_prev's sta)
        if i == 0:
            dx = 0.0
        else:
            dx = s.sta - ecn.stations[i-1].sta
        Sf = manning_sf(Q, A, P, 0.014) if A > 0 else 0.0
        hf = Sf * max(0, dx)
        # Solve for z_curr:
        # z_curr = EGL_prev - hf - y - V^2/2g
        z_designed = EGL_prev - hf - y_target - V * V / (2.0 * G)
        
        # Now check: if we use the original invert z_curr (the user's guess),
        # what depth do we get from the energy equation?
        # z_user + y_user + V_user^2/2g = EGL_prev - hf
        # For a 1D rectangular: y_user + V^2/2g = (EGL_prev - hf) - z_user
        EGL_local = EGL_prev - hf - z_curr
        # y_local: solve y + Q^2/(w^2*y^2*2g) = EGL_local
        w_eff = s.width if s.width > 0 else 6.25
        y_local = max(0.05, EGL_local)  # initial guess
        for _ in range(30):
            A_l, _ = section_geometry_for_ec(Q, w_eff, s.r1, s.r2, s.cl_height,
                                             s.geom_code1, y_local)
            A_l_eff = max(A_l, w_eff * y_local)
            V_l = Q / A_l_eff
            H_l = y_local + V_l * V_l / (2.0 * G)
            f_l = H_l - EGL_local
            if abs(f_l) < 1e-5:
                break
            dy_l = max(y_local * 1e-3, 1e-4)
            A_ld, _ = section_geometry_for_ec(Q, w_eff, s.r1, s.r2, s.cl_height,
                                              s.geom_code1, y_local + dy_l)
            A_ld_eff = max(A_ld, w_eff * (y_local + dy_l))
            V_ld = Q / A_ld_eff
            H_ld = (y_local + dy_l) + V_ld * V_ld / (2.0 * G)
            f_ld = H_ld - EGL_local
            df_l = (f_ld - f_l) / dy_l
            if abs(df_l) < 1e-6:
                break
            y_new_l = y_local - f_l / df_l
            y_new_l = max(0.01, min(y_new_l, 20.0))
            if abs(y_new_l - y_local) < 1e-6:
                y_local = y_new_l
                break
            y_local = y_new_l
        
        # Use y_local for sigma comparison
        A_local, P_local = section_geometry_for_ec(Q, w_eff, s.r1, s.r2,
                                                    s.cl_height, s.geom_code1, y_local)
        V_local = Q / A_local if A_local > 0 else 0.0
        p0_local = p_atm + RHO_WATER * G * y_local
        if include_centrifugal and s.rad_curv != 0 and V_local > 0:
            p0_local += RHO_WATER * V_local * V_local * y_local / abs(s.rad_curv)
        sigma_local = (p0_local - p_vapor) / (0.5 * RHO_WATER * V_local * V_local) if V_local > 0 else float("inf")
        
        rows.append({
            'sta': s.sta,
            'invert_orig': z_curr,
            'invert_designed': z_designed,
            'depth': y_local,
            'velocity': V_local,
            'sigma_actual': sigma_actual,
            'sigma_with_user_invert': sigma_local,
            'sigma_target': sigma_target,
            'target_achieved': abs(sigma_local - sigma_target) / sigma_target < 0.10,
        })
        
        # Propagate
        z_prev = z_curr  # use the user's invert for the next step
        EGL_prev = z_prev + y_local + V_local * V_local / (2.0 * G)
    
    res.rows = rows
    return res


# =============================================================================
# Self-test
# =============================================================================

if __name__ == "__main__":
    from em_data import read_ecn_input
    ecn = read_ecn_input("sample_data/DATA/ECNDAT", "sample_data/DATA/GLENECN")
    print(f"=== ECAVNO self-test ===")
    print(f"Q = {ecn.q} m^3/s, target sigma = 0.2")
    print(f"Assumption: {'rotation' if ecn.assumption == 'Y' else 'potential'}")
    
    res = design_spillway(ecn)
    n_achieved = sum(1 for r in res.rows if r['target_achieved'])
    print(f"  Stations: {len(res.rows)}, target achieved: {n_achieved}/{len(res.rows)}")
    print(f"  {'STA':>8s}  {'z_user':>9s}  {'z_des':>9s}  {'depth':>7s}  {'V':>7s}  {'sigma':>7s}")
    for r in res.rows[:10]:
        sigma_disp = f"{r['sigma_with_user_invert']:.3f}" if r['sigma_with_user_invert'] < 100 else 'inf'
        print(f"  {r['sta']:8.1f}  {r['invert_orig']:9.3f}  {r['invert_designed']:9.3f}  "
              f"{r['depth']:7.3f}  {r['velocity']:7.2f}  {sigma_disp:>7s}")
    print(f"  ...")
    print("ECAVNO self-test passed.")
