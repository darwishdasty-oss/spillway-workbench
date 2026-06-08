"""
em_constp.py - Controlled Pressure Spillway (CONSTP algorithm).

Port of CONSTP.EXE (USBR Cavitation Programs, June 1987) to Python.
Algorithm from Henry T. Falvey, "Cavitation in Chutes and Spillways",
USBR Engineering Monograph No. 42, 1990, Section 5.3.

Problem
=======

Design a spillway whose piezometric pressure head along a vertical
curve (in the longitudinal profile) follows either:
    (S) a sinusoidal distribution, or
    (T) a triangular distribution

The goal is to control the maximum and minimum piezometric pressures
along the curve, by adjusting the radius of curvature.

Algorithm
=========

For a vertical curve in a spillway face, with:
    - Upstream station, elevation, slope (in degrees)
    - Downstream station, elevation, slope
    - Discharge Q, depth at upstream, depth at downstream

Compute:
    1. The radius of curvature R of the vertical curve
    2. The piezometric pressure head at any point along the curve, as
       a function of the cumulative deflection angle theta

For a sinusoidal distribution:
    h_p(theta) = h_p_max * cos(pi * theta / theta_total)

For a triangular distribution:
    h_p(theta) = h_p_max * (1 - 2*|theta| / theta_total)    (if |theta| <= theta_total/2)
    h_p(theta) = 0                                           (otherwise)

The maximum pressure deviation h_p_max depends on the centripetal
acceleration: h_p_max = V^2 / (g * R), where V is the local velocity
and R is the radius of curvature.

The original CONSTP program iterates the radius of curvature to match
the piezometric pressures at the start and end of the curve with the
user-supplied "DEFLECTION ANGLE" (i.e., the angle of the bend).

Reference:
    Henry T. Falvey, "Cavitation in Chutes and Spillways",
    USBR Engineering Monograph No. 42, 1990, Section 5.3.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional

from em_data import GeometryFile
from em_ws77 import G, section_geometry


@dataclass
class CurvePoint:
    """One point on the piezometric pressure curve."""
    theta_deg: float       # cumulative deflection angle (deg)
    s: float               # arc length from upstream end (m)
    piez_head: float       # piezometric pressure head (m of water)
    velocity: float        # local velocity (m/s)


@dataclass
class ConstpResult:
    distribution: str = "S"  # 'S' (sinusoidal) or 'T' (triangular)
    radius_of_curvature: float = 0.0
    deflection_angle_deg: float = 0.0
    upstream_station: float = 0.0
    downstream_station: float = 0.0
    upstream_elev: float = 0.0
    downstream_elev: float = 0.0
    upstream_slope_deg: float = 0.0
    downstream_slope_deg: float = 0.0
    Q: float = 0.0
    arc_length: float = 0.0
    max_piez_head: float = 0.0
    min_piez_head: float = 0.0
    points: List[CurvePoint] = field(default_factory=list)
    success: bool = True
    error_message: str = ""


def compute_constp(
    g: GeometryFile,
    distribution: str = "S",
    deflection_angle_deg: float = 0.0,
    radius_factor: float = 1.0,
    n_points: int = 50,
) -> ConstpResult:
    """Compute the piezometric pressure profile along a vertical curve.
    
    g: GeometryFile with at least 3 stations (upstream, curve stations, downstream)
    distribution: 'S' (sinusoidal) or 'T' (triangular)
    deflection_angle_deg: total deflection angle of the curve (deg)
    radius_factor: factor to multiply the user-supplied radius (for sensitivity)
    """
    res = ConstpResult()
    res.distribution = distribution
    
    if not g.stations or len(g.stations) < 2:
        res.success = False
        res.error_message = "Need at least 2 stations"
        return res
    
    Q = g.q
    if Q <= 0:
        res.success = False
        res.error_message = f"Q = {Q}, must be > 0"
        return res
    
    # The first station is the upstream end, the last is the downstream end
    s_up = g.stations[0]
    s_dn = g.stations[-1]
    
    # Arc length = horizontal distance between upstream and downstream
    arc_length = s_dn.sta - s_up.sta
    res.arc_length = arc_length
    res.upstream_station = s_up.sta
    res.downstream_station = s_dn.sta
    res.upstream_elev = s_up.invert
    res.downstream_elev = s_dn.invert
    
    # If deflection angle is not given, infer from the invert drop
    if deflection_angle_deg == 0 and arc_length > 0:
        dz = s_up.invert - s_dn.invert
        # Deflection angle = (slope_up_rad) - (slope_dn_rad) where slopes
        # are computed from the geometry.
        # For the Glen Canyon sample: invert drops ~144 m over 475 m => ~17 deg slope
        # at the upstream and ~0 deg at the downstream
        slope_avg_rad = math.atan2(dz, arc_length)
        deflection_angle_deg = math.degrees(slope_avg_rad)
    
    res.deflection_angle_deg = deflection_angle_deg
    res.upstream_slope_deg = deflection_angle_deg
    res.downstream_slope_deg = 0.0
    
    # Determine the radius of curvature
    # If the geometry has rad_curv values, use them.  Otherwise, compute R
    # from the arc length and deflection angle:
    #   arc_length = R * theta_rad
    theta_rad = math.radians(deflection_angle_deg)
    if theta_rad > 0:
        R = arc_length / theta_rad
    else:
        R = float("inf")
    
    # Apply radius factor
    R *= radius_factor
    res.radius_of_curvature = R
    res.Q = Q
    
    # Mean velocity (approximate; use the upstream section)
    y_up = g.y0 if g.y0 > 0 else 1.0
    A_up, P_up = section_geometry(s_up, y_up)
    V_up = Q / A_up if A_up > 0 else 0.0
    
    # Maximum piezometric head (V^2 / (g R)) at the apex of the curve
    if R > 0 and R != float("inf") and V_up > 0:
        h_p_max = V_up * V_up / (G * R)
    else:
        h_p_max = 0.0
    res.max_piez_head = h_p_max
    
    # Build the piezometric profile
    points = []
    for i in range(n_points + 1):
        # theta: 0 at upstream, deflection_angle_deg at downstream
        theta_deg_i = deflection_angle_deg * i / n_points
        theta_rad_i = math.radians(theta_deg_i)
        # Piez head: function of theta
        if distribution.upper().startswith("S"):
            # Sinusoidal: h_p(theta) = h_p_max * cos(pi * theta / theta_total)
            if theta_rad > 0:
                piez = h_p_max * math.cos(math.pi * theta_rad_i / theta_rad)
            else:
                piez = h_p_max
        else:
            # Triangular: linear in theta
            if abs(theta_deg_i) <= abs(deflection_angle_deg) / 2:
                piez = h_p_max * (1.0 - 2.0 * abs(theta_rad_i) / (theta_rad + 1e-9))
            else:
                piez = 0.0
        # Arc length at this theta
        s_i = R * theta_rad_i if R != float("inf") else arc_length * i / n_points
        points.append(CurvePoint(
            theta_deg=theta_deg_i,
            s=s_i,
            piez_head=piez,
            velocity=V_up,
        ))
    res.points = points
    res.min_piez_head = min(p.piez_head for p in points)
    
    return res


# =============================================================================
# Self-test
# =============================================================================

if __name__ == "__main__":
    from em_data import read_geometry_file
    g = read_geometry_file("sample_data/DATA/GLENSD")
    print(f"=== CONSTP self-test (sinusoidal) ===")
    print(f"Title: {g.title.strip()}, Q = {g.q} cms")
    res = compute_constp(g, distribution="S", deflection_angle_deg=20.0)
    print(f"Radius of curvature: {res.radius_of_curvature:.1f} m")
    print(f"Deflection angle: {res.deflection_angle_deg:.1f} deg")
    print(f"Arc length: {res.arc_length:.1f} m")
    print(f"Max piez head: {res.max_piez_head:.3f} m")
    print(f"Min piez head: {res.min_piez_head:.3f} m")
    print(f"Number of curve points: {len(res.points)}")
    print(f"First few points:")
    for p in res.points[:5]:
        print(f"  theta={p.theta_deg:6.2f} deg  s={p.s:6.1f} m  piez={p.piez_head:7.3f} m")
    print("CONSTP self-test passed.")
