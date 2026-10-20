"""
em_air.py - Air entrainment / aerator analysis.

Implements simplified USBR (Falvey 1990) air-demand models:
  - Aerator jet trajectory gives sub-atmospheric pressure zone
  - Air flow rate scales with V^0.5 and chute geometry
  - Q_air/Q_water is the usual reporting metric

References:
  - Falvey, H.T. (1990), Cavitation in Chutes and Spillways, USBR Mono 42, Ch. 8
  - USBR Design of Small Dams (1987), Ch. 9 on spillway aerators
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

G = 9.807
RHO_AIR = 1.225
RHO_WATER = 998.2


@dataclass
class AeratorResult:
    """Result of a single aerator analysis."""
    sta: float
    invert: float
    velocity: float
    depth: float
    air_flow_cms: float            # Q_air in m^3/s
    beta: float                    # Q_air / Q_water
    sub_atm_pressure_pa: float     # magnitude of pressure drop
    jet_trajectory_m: float        # downstream throw distance
    max_height_m: float            # max jet height above invert


def beta_woerner(V: float, g: float = G) -> float:
    """USBR-Woerner empirical formula for Q_air/Q_water.
    
    beta = 0.024 * (V^2 / g*y)^0.5   (for V in m/s, y in m)
    Only valid for V > 5 m/s.
    """
    if V < 5.0:
        return 0.0
    Fr = V * V / (g * 1.0)
    return min(0.6, 0.024 * math.sqrt(Fr))


def beta_pfister(V: float, q: float) -> float:
    """Pfister 2011 air-entrainment model.
    
    beta = 0.057 * (V - 1.5)^0.5  for  V > 1.5 m/s
    """
    if V <= 1.5:
        return 0.0
    return min(0.6, 0.057 * math.sqrt(V - 1.5))


def air_demand_simple(V: float, q: float, jump_height: float = 0.5,
                      ramp_angle_deg: float = 11.3) -> AeratorResult:
    """Compute air demand for a single aerator with a ramp + offset.
    
    Parameters:
        V: approach velocity (m/s)
        q: unit discharge (m^2/s)
        jump_height: ramp height (m)
        ramp_angle_deg: ramp angle from horizontal
    
    Returns: AeratorResult with all fields populated.
    """
    if V <= 0 or q <= 0:
        return AeratorResult(0, 0, V, 0, 0, 0, 0, 0, 0)

    # Jet trajectory (ballistic)
    y = jump_height
    angle_rad = math.radians(ramp_angle_deg)
    Vx = V * math.cos(angle_rad)
    Vy = V * math.sin(angle_rad)
    # y(t) = y0 + Vy*t - 0.5*g*t^2 = 0
    if Vy * Vy + 2 * G * y > 0:
        t_flight = (Vy + math.sqrt(Vy * Vy + 2 * G * y)) / G
    else:
        t_flight = 0
    Lx = Vx * t_flight
    t_max = Vy / G
    max_h = y + Vy * t_max - 0.5 * G * t_max * t_max

    # Sub-atmospheric pressure under the jet (simplified)
    # p_drop ~ 0.5 * rho * V^2 * sin^2(angle)
    p_drop = 0.5 * RHO_WATER * V * V * math.sin(angle_rad) ** 2

    # Air demand
    Q_water = q
    beta = beta_woerner(V)
    Q_air = beta * Q_water
    return AeratorResult(
        sta=0, invert=0, velocity=V, depth=q / V if V > 0 else 0,
        air_flow_cms=Q_air, beta=beta,
        sub_atm_pressure_pa=p_drop,
        jet_trajectory_m=Lx, max_height_m=max_h,
    )


def air_demand_profile(profile_rows: List[dict],
                        aerator_sta: float = 720.0,
                        aerator_height: float = 0.5,
                        aerator_angle_deg: float = 11.3,
                        ) -> List[AeratorResult]:
    """Compute air demand at all stations, treating one station as the
    aerator and propagating the air-concentration downstream.
    """
    results = []
    aerator_data = None
    for r in profile_rows:
        V = r.get("velocity", 0)
        Q = r.get("q_cms", 0) or r.get("Q", 0) or 0
        if Q == 0:
            # Estimate q from y and V
            y = r.get("depth", 0)
            if y > 0 and V > 0:
                q = V * y
                Q = q
        if abs(r["sta"] - aerator_sta) < 1.0:
            res = air_demand_simple(V, Q, aerator_height, aerator_angle_deg)
            res.sta = r["sta"]
            res.invert = r["invert"]
            results.append(res)
            aerator_data = res
        elif aerator_data is not None and r["sta"] > aerator_sta:
            # Air concentration decays downstream (1/2 life ~ 50 m)
            decay = 0.5 ** ((r["sta"] - aerator_sta) / 50.0)
            beta = aerator_data.beta * decay
            Q_air = beta * (Q if Q > 0 else (V * r["depth"]))
            res = AeratorResult(
                sta=r["sta"], invert=r["invert"], velocity=V, depth=r["depth"],
                air_flow_cms=Q_air, beta=beta,
                sub_atm_pressure_pa=0, jet_trajectory_m=0, max_height_m=0,
            )
            results.append(res)
        else:
            results.append(AeratorResult(
                sta=r["sta"], invert=r["invert"], velocity=V, depth=r["depth"],
                air_flow_cms=0, beta=0, sub_atm_pressure_pa=0,
                jet_trajectory_m=0, max_height_m=0,
            ))
    return results


if __name__ == "__main__":
    # Self-test
    print("=== Air entrainment self-test ===")
    for V in [10, 15, 20, 25, 30, 35, 40]:
        res = air_demand_simple(V, V * 1.0)
        print(f"  V={V:5.1f} m/s  Q_air={res.air_flow_cms:7.4f} cms  "
              f"beta={res.beta:.4f}  L={res.jet_trajectory_m:.2f} m  "
              f"p_drop={res.sub_atm_pressure_pa/1000:.1f} kPa")
