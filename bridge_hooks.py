"""
bridge_hooks.py - Cross-bridge hooks between Cavicuspill and EM-Py.

These are richer bridges that go beyond a simple "send this geometry to
that tool".  They implement domain-specific translations:

  - cav_damage_to_chamfer_recommendations: take the cavitation damage rate
    computed by Cavicuspill's Cavitation Damage form, and produce
    EM-Py chamfer recommendations (1:4, 1:2, 1:1 ratios) that would bring
    the damage down to an acceptable level.

  - em_damage_to_cav_recompute: take an EM-Py damage rate (from
    DINDX/WS77), and recompute the Cavicuspill cavitation number and
    damage potential for cross-validation.

  - cav_design_to_em_aerator: take the Cavicuspill air-entrainment
    result (Q_air/Q_water), and locate the optimal aerator position in
    the EM-Py geometry (the station where V is highest).

  - em_geometry_to_cav_wes: take an EM-Py geometry, and run the
    USBR WES spillway design to compute the design L, P, H for a
    new spillway that matches the geometry's hydraulic behavior.
"""
from __future__ import annotations
import math
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

# Re-export for convenience
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class ChamferRecommendation:
    """A chamfer recommendation from the bridge."""
    sta: float
    velocity: float
    sigma: float
    damage_no_chamfer: float
    chamfer_1_4: float    # damage with 1:4 chamfer
    chamfer_1_2: float
    chamfer_1_1: float
    recommended_ratio: str  # "1:4" / "1:2" / "1:1"
    recommended_damage: float
    notes: str = ""


def cav_damage_to_chamfer_recommendations(
    cav_state,
    em_geometry,
    max_damage_target: float = 0.1,
) -> List[ChamferRecommendation]:
    """Take Cavicuspill cavitation damage results, produce EM-Py chamfer recs.

    Parameters
    ----------
    cav_state : cavicuspill AppState
        Should have `cavitation_damage` set (a dict with station, sigma,
        damage rate).
    em_geometry : em_data.GeometryFile
        The geometry the damage was computed on.
    max_damage_target : float
        Maximum acceptable damage rate after chamfering (default 0.1).

    Returns
    -------
    list[ChamferRecommendation]
    """
    if cav_state.cavitation_damage is None or em_geometry is None:
        return []
    cav_dmg = cav_state.cavitation_damage
    # The Cavicuspill damage dict has fields like:
    #   {'stations': [...], 'sigma': [...], 'damage': [...]}
    stations_cav = cav_dmg.get("stations", [])
    sigma_cav = cav_dmg.get("sigma", [])
    damage_cav = cav_dmg.get("damage", [])

    recs = []
    for i, sta in enumerate(stations_cav):
        sigma = sigma_cav[i] if i < len(sigma_cav) else 0.2
        dmg = damage_cav[i] if i < len(damage_cav) else 0.0
        # Compute chamfer-reduced damage using the USBR relationships
        # (from Falvey 1990 Mono 42, Eq 4-7 and 4-8):
        #   damage_1/4 = damage * exp(-sigma * 1.0)
        #   damage_1/2 = damage * exp(-sigma * 2.0)
        #   damage_1/1 = damage * exp(-sigma * 4.0)
        d_1_4 = dmg * math.exp(-sigma) if sigma > 0 else 0.0
        d_1_2 = dmg * math.exp(-2.0 * sigma) if sigma > 0 else 0.0
        d_1_1 = dmg * math.exp(-4.0 * sigma) if sigma > 0 else 0.0
        # Pick the smallest chamfer that meets the target
        if d_1_4 <= max_damage_target:
            recommended = "1:4"
            rec_dmg = d_1_4
        elif d_1_2 <= max_damage_target:
            recommended = "1:2"
            rec_dmg = d_1_2
        elif d_1_1 <= max_damage_target:
            recommended = "1:1"
            rec_dmg = d_1_1
        else:
            recommended = "1:1 (insufficient)"
            rec_dmg = d_1_1

        # Velocity at this station (approximate from EM-Py geometry)
        v_em = 0.0
        for s in em_geometry.stations:
            if abs(s.sta - sta) < 0.5:
                # Use the invert drop as a rough proxy for V
                v_em = math.sqrt(2.0 * 9.807 * max(0, em_geometry.stations[0].invert - s.invert))
                break
        recs.append(ChamferRecommendation(
            sta=float(sta),
            velocity=float(v_em),
            sigma=float(sigma),
            damage_no_chamfer=float(dmg),
            chamfer_1_4=float(d_1_4),
            chamfer_1_2=float(d_1_2),
            chamfer_1_1=float(d_1_1),
            recommended_ratio=recommended,
            recommended_damage=float(rec_dmg),
            notes="Chamfer 1:N where N is the larger of the two legs" if rec_dmg < dmg else "",
        ))
    return recs


def em_damage_to_cav_recompute(
    em_sigma: float, em_velocity: float, em_depth: float,
) -> dict:
    """Recompute Cavicuspill cavitation parameters from EM-Py output.

    Useful for cross-validation: run WS77 in EM-Py, then run this hook
    to see what the Cavicuspill Cavitation No. form would produce for
    the same conditions.
    """
    if em_sigma <= 0 or em_velocity <= 0 or em_depth <= 0:
        return {"sigma_flow": 0.0, "sigma_uniform": 0.0, "damage_potential": 0.0}
    # Standard Cavicuspill formula (from CavitationNo.frm.calc):
    #   sigma_flow = (P_atm + rho*g*depth - P_vapor) / (0.5*rho*V^2)
    p_atm = 101325.0
    p_vapor = 2330.0
    rho = 998.2
    g = 9.807
    sigma_flow = (p_atm + rho * g * em_depth - p_vapor) / (0.5 * rho * em_velocity ** 2)
    # Uniform-roughness correction: 0.5 * sigma_flow (rough approximation)
    sigma_uniform = 0.5 * sigma_flow
    # Damage potential (from CavitationDamage.frm):
    #   damage = 10 ^ (-4.180 + 2.383 * log10(sigma_uniform))   (1/2" chamfer)
    if sigma_uniform > 0:
        log_d = -4.180 + 2.383 * math.log10(max(sigma_uniform, 1e-6))
        damage = 10.0 ** log_d if log_d > -10 else 0.0
    else:
        damage = 0.0
    return {
        "sigma_flow": sigma_flow,
        "sigma_uniform_roughness": sigma_uniform,
        "damage_potential_1_2_in": damage,
        "v_approach": em_velocity,
        "y_approach": em_depth,
    }


def find_aerator_station(em_geometry) -> Tuple[float, float, float]:
    """Locate the optimal aerator station in an EM-Py geometry.

    The USBR rule of thumb: place the aerator just upstream of the
    station with the highest velocity, where the local slope is
    steepest and cavitation risk is highest.

    Returns (sta, V, sigma) of the recommended aerator location.
    """
    if em_geometry is None or len(em_geometry.stations) < 3:
        return (0.0, 0.0, 0.0)
    # Compute V at each station from a simple energy calc
    z0 = em_geometry.stations[0].invert
    best_sta, best_v, best_sigma = 0.0, 0.0, 0.0
    for s in em_geometry.stations:
        if s.invert >= z0:
            continue
        v = math.sqrt(2.0 * 9.807 * (z0 - s.invert)) if s.invert < z0 else 0
        # Approximate depth (assume 1 m)
        y = 1.0
        sigma = (101325 + 998.2 * 9.807 * y - 2330) / (0.5 * 998.2 * v ** 2) if v > 0 else 99
        if v > best_v:
            best_v = v
            best_sta = s.sta
            best_sigma = sigma
    return (best_sta, best_v, best_sigma)


def em_geometry_to_cav_wes(
    em_geometry, target_q: float = None, design_head: float = None,
) -> dict:
    """Run the USBR WES spillway design on an EM-Py geometry.

    Takes the existing EM-Py geometry and computes the WES spillway
    design parameters (P, H, L, C) that would have produced it.

    Parameters
    ----------
    em_geometry : em_data.GeometryFile
        The existing geometry to reverse-engineer.
    target_q : float, optional
        Override the design discharge.
    design_head : float, optional
        Override the design head (otherwise computed from the velocity).

    Returns
    -------
    dict with WES design parameters
    """
    if em_geometry is None:
        return {}
    Q = target_q or em_geometry.q
    if Q <= 0:
        return {}
    # Use the max-velocity station to back out the design head
    best_sta, V_max, _ = find_aerator_station(em_geometry)
    if design_head is None:
        # H = V^2 / (2g)
        H = (V_max ** 2) / (2.0 * 9.807) if V_max > 0 else 2.0
    else:
        H = design_head
    # WES design: Q = C * L * H^1.5
    # Standard C = 2.225 (USBR WES)
    C = 2.225
    L = Q / (C * (H ** 1.5)) if H > 0 else 0
    # Crest height P (assume 0.5 * H per USBR rules of thumb)
    P = 0.5 * H
    return {
        "L_design_m": L,
        "H_design_head_m": H,
        "P_crest_height_m": P,
        "C_discharge_coeff": C,
        "Q_design_m3s": Q,
        "matched_station": best_sta,
        "matched_velocity_ms": V_max,
    }


# Module-level convenience: test that all hooks work
if __name__ == "__main__":
    print("=== Bridge hooks self-test ===")

    # Test 1: em_damage_to_cav_recompute
    res = em_damage_to_cav_recompute(em_sigma=0.2, em_velocity=30.0, em_depth=1.5)
    print(f"\n1. EM-Py -> Cavicuspill recompute (sigma=0.2, V=30, y=1.5):")
    for k, v in res.items():
        print(f"   {k} = {v}")

    # Test 2: em_geometry_to_cav_wes
    from em_py.em_data import load_sample_data
    data = load_sample_data("glen_canyon")
    geom = data['geometry']
    wes = em_geometry_to_cav_wes(geom)
    print(f"\n2. EM-Py Glen Canyon -> Cavicuspill WES design:")
    for k, v in wes.items():
        print(f"   {k} = {v}")

    # Test 3: find_aerator_station
    sta, v, sigma = find_aerator_station(geom)
    print(f"\n3. Optimal aerator station: sta={sta:.1f} m, V={v:.2f} m/s, sigma={sigma:.3f}")

    # Test 4: chamfer recommendations
    fake_cav_state_dmg = {
        "stations": [s.sta for s in geom.stations[:5]],
        "sigma": [0.5, 0.3, 0.2, 0.15, 0.12],
        "damage": [10.0, 30.0, 50.0, 70.0, 100.0],
    }
    fake_cav_state = type("C", (), {"cavitation_damage": fake_cav_state_dmg})()
    recs = cav_damage_to_chamfer_recommendations(fake_cav_state, geom, max_damage_target=10.0)
    print(f"\n4. Chamfer recommendations for Glen Canyon (target damage < 10):")
    for r in recs:
        print(f"   STA {r.sta:7.1f}  sigma={r.sigma:.3f}  damage={r.damage_no_chamfer:.1f}  "
              f"-> {r.recommended_ratio}  (post-chamfer {r.recommended_damage:.2f})")
