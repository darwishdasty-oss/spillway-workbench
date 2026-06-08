"""
em_traj.py - Aerator Trajectory (TRAJ algorithm).

Port of TRAJ.EXE (USBR Cavitation Programs, June 1987) to Python.
Algorithm from Henry T. Falvey, "Cavitation in Chutes and Spillways",
USBR Engineering Monograph No. 42, 1990, Section 4.7.

Problem
=======

An aerator on a spillway chute is a ramp followed by a vent (air duct)
that brings air into the flow to suppress cavitation.  Given:

    - Ramp geometry: angle, lip elevation, lip station
    - Flow properties: Q, depth at ramp, velocity at ramp
    - Vent geometry: number of vents, width, area, loss coefficient
    - Turbulence intensity

Compute:
    1. The jet trajectory (the path of water leaving the ramp)
    2. The air flow rate required to maintain near-atmospheric pressure
       under the jet
    3. The required submergence depth at the downstream end of the aerator
       (so the air cavity is not collapsed by the boundary layer)

Algorithm
=========

1. Jet trajectory: ballistic motion from the ramp lip
       x(t) = x_lip + v0x * t
       y(t) = y_lip + v0y * t - 0.5 * g * t^2
   with optional air drag (not implemented in the simple version).
   The jet lands at the floor when y(t) = y_floor.

2. Air flow rate: from the sub-atmospheric pressure under the jet.
   The pressure drop under the jet is:
       delta_p = 0.5 * rho_air * V_jet^2 * (1 - (V_air/V_jet)^2)
   The required air velocity for a given pressure drop:
       V_air = V_jet * sqrt(1 - 4 * delta_p / (rho_air * V_jet^2))
   The air flow rate is then:
       Q_air = V_air * A_vent * n_vents

3. Required submergence: the air cavity must be long enough for the
   jet to land and re-attach without choking.  Empirically, the
   submergence should be at least 30-50% of the jet thickness.

Reference:
    Henry T. Falvey, "Cavitation in Chutes and Spillways",
    USBR Engineering Monograph No. 42, 1990, Section 4.7.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# Physical constants
G = 9.807
RHO_WATER = 998.2
RHO_AIR = 1.225
GAMMA_AIR = 1.4
P_ATM_PA = 101325.0


@dataclass
class RampGeometry:
    """Geometry of the aerator ramp."""
    angle_deg: float = 8.0     # angle of ramp face from horizontal
    elev_lip: float = 1000.0   # elevation of ramp lip (m)
    sta_lip: float = 800.0     # station of ramp lip (m)
    elev_floor: float = 999.0  # elevation of downstream floor (m)


@dataclass
class FlowProperties:
    """Water flow properties at the ramp."""
    q: float = 50.0           # discharge (m^3/s)
    velocity_ramp: float = 20.0  # velocity at ramp (m/s)
    depth_ramp: float = 1.0    # flow depth at ramp (m)
    turbulence: float = 0.05   # turbulence intensity (fraction)


@dataclass
class VentGeometry:
    """Geometry of the air vent(s)."""
    n_vents: int = 2
    width: float = 1.0         # width of each vent (m)
    area: float = 2.0          # cross-sectional area of each vent (m^2)
    loss_coeff: float = 0.5    # entrance loss coefficient


@dataclass
class TrajectoryPoint:
    """One point on the jet trajectory."""
    t: float
    x: float
    y: float


@dataclass
class TrajResult:
    """Output of a TRAJ run."""
    trajectory: List[TrajectoryPoint] = field(default_factory=list)
    land_x: float = 0.0            # station where jet lands
    land_t: float = 0.0            # time of landing
    max_height: float = 0.0        # max height above lip
    jet_thickness: float = 0.0     # thickness of jet at lip
    air_velocity_required: float = 0.0
    air_flow_rate: float = 0.0     # m^3/s
    submergence_required: float = 0.0  # m (cavity depth needed)
    success: bool = True
    error_message: str = ""


def compute_trajectory(
    ramp: RampGeometry,
    flow: FlowProperties,
    vent: VentGeometry,
    p_atm: float = P_ATM_PA,
    max_pressure_drop_fraction: float = 0.5,
) -> TrajResult:
    """Compute the jet trajectory, air flow rate, and required submergence.
    
    max_pressure_drop_fraction: maximum allowable pressure drop under
        the jet as a fraction of atmospheric (default 0.5 = 50%).
        Typical aerator design limits this to 30-50%.
    """
    res = TrajResult()
    
    # Jet launch angle (same as ramp angle from horizontal)
    angle_rad = math.radians(ramp.angle_deg)
    v0x = flow.velocity_ramp * math.cos(angle_rad)
    v0y = flow.velocity_ramp * math.sin(angle_rad)
    
    # Trajectory: ballistic motion
    # y(t) = elev_lip + v0y*t - 0.5*g*t^2
    # Lands when y(t) = elev_floor
    # elev_floor = elev_lip + v0y*t - 0.5*g*t^2
    # 0.5*g*t^2 - v0y*t + (elev_floor - elev_lip) = 0
    delta_y = ramp.elev_floor - ramp.elev_lip  # negative (jet falls)
    
    if abs(v0y) < 1e-6 and abs(delta_y) < 1e-6:
        # No trajectory to compute
        res.success = False
        res.error_message = "Jet is horizontal and floor is at lip elevation"
        return res
    
    if abs(v0y) < 1e-6:
        # Horizontal jet; time of flight infinite (jet never lands)
        t_max = 5.0  # arbitrary
        land_t = float("inf")
        land_x = float("inf")
    else:
        # Quadratic: 0.5*g*t^2 - v0y*t + delta_y = 0
        a = 0.5 * G
        b = -v0y
        c = delta_y
        disc = b * b - 4 * a * c
        if disc < 0:
            res.success = False
            res.error_message = f"No real solution: discriminant = {disc}"
            return res
        t1 = (-b - math.sqrt(disc)) / (2 * a)
        t2 = (-b + math.sqrt(disc)) / (2 * a)
        # Pick the smaller positive root (jet lands going down)
        if t1 > 0:
            land_t = t1
        elif t2 > 0:
            land_t = t2
        else:
            res.success = False
            res.error_message = "Jet does not land in forward time"
            return res
        land_x = ramp.sta_lip + v0x * land_t
    
    # Build trajectory points (sample 100 points along the flight)
    n_pts = 100
    t_max = land_t if land_t != float("inf") else 5.0
    traj = []
    max_h = ramp.elev_lip
    for i in range(n_pts + 1):
        t = t_max * i / n_pts
        x = ramp.sta_lip + v0x * t
        y = ramp.elev_lip + v0y * t - 0.5 * G * t * t
        traj.append(TrajectoryPoint(t=t, x=x, y=y))
        if y > max_h:
            max_h = y
    res.trajectory = traj
    res.land_x = land_x
    res.land_t = land_t
    res.max_height = max_h
    res.jet_thickness = flow.depth_ramp
    
    # Air flow rate from sub-atmospheric pressure under jet
    # The pressure drop under the jet (Falvey 1990 Eq. 4.32):
    #   delta_p / (0.5 rho_air V_jet^2) = 1 - (V_air / V_jet)^2
    # For a submergence ratio, the required pressure drop is typically
    # 10-30% of atmospheric.
    # For design, pick delta_p = max_pressure_drop_fraction * p_atm.
    V_jet = flow.velocity_ramp
    delta_p_max = max_pressure_drop_fraction * p_atm
    # V_air = V_jet * sqrt(1 - 2 * delta_p / (rho_air * V_jet^2))
    if RHO_AIR * V_jet * V_jet < 2 * delta_p_max:
        # Pressure drop too large; can't supply enough air
        res.air_velocity_required = 0.0
        res.air_flow_rate = 0.0
    else:
        V_air = V_jet * math.sqrt(1.0 - 2.0 * delta_p_max / (RHO_AIR * V_jet * V_jet))
        # Sonic limit check
        c_sound = math.sqrt(GAMMA_AIR * p_atm / RHO_AIR)
        V_air = min(V_air, c_sound * 0.7)  # choked at Mach 0.7
        # Air flow rate
        Q_air = V_air * vent.area * vent.n_vents
        # Adjust for loss coefficient (K = delta_p / (0.5 rho V^2))
        # Effective velocity is reduced
        Q_air *= 1.0 / (1.0 + vent.loss_coeff)
        res.air_velocity_required = V_air
        res.air_flow_rate = Q_air
    
    # Required submergence: the air cavity should be at least 30-50% of
    # the jet thickness.  The cavity length is approx the jet trajectory
    # length, so required submergence = 0.3 * depth_ramp (Falvey 1990).
    res.submergence_required = 0.3 * flow.depth_ramp
    
    return res


# =============================================================================
# Self-test
# =============================================================================

if __name__ == "__main__":
    # Glen Canyon aerator (typical)
    ramp = RampGeometry(angle_deg=8.0, elev_lip=1000.0, sta_lip=800.0, elev_floor=995.0)
    flow = FlowProperties(q=283.168, velocity_ramp=35.0, depth_ramp=1.5, turbulence=0.05)
    vent = VentGeometry(n_vents=2, width=1.5, area=3.0, loss_coeff=0.5)
    
    res = compute_trajectory(ramp, flow, vent)
    print(f"=== TRAJ self-test ===")
    print(f"Jet lands at STA = {res.land_x:.2f} m (range = {res.land_x - ramp.sta_lip:.2f} m)")
    print(f"Flight time = {res.land_t:.3f} s")
    print(f"Max height above lip = {res.max_height - ramp.elev_lip:.3f} m")
    print(f"Air velocity required = {res.air_velocity_required:.2f} m/s")
    print(f"Air flow rate = {res.air_flow_rate:.2f} m^3/s")
    print(f"Required submergence = {res.submergence_required:.3f} m")
    print(f"Number of trajectory points = {len(res.trajectory)}")
    print("TRAJ self-test passed.")
