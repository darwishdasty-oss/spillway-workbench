"""
em_dindx.py - Damage Index calculator (DINDX tool).

Ported from DINDX.EXE (Bureau of Reclamation Cavitation Programs, June 1987).
Henry T. Falvey, USBR.

The original DINDX.EXE is an INTERACTIVE program: the user types in
    (discharge, cavitation_potential) pairs, and the program returns
    (a) a damage index curve fit, and
    (b) the cumulative damage potential as a function of time
    when a hydrograph is given.

Algorithm (from the source, comments in the FORTRAN):
    1. Input at least 3 (Q, sigma) data points, BEGIN WITH MAX FLOW
       AND END WITH 0.
    2. Fit log(sigma) = A + B*log(Q) by least squares.
    3. For each station, the damage potential is
           D(Q) = 10**(C + D*log10(sigma))
       where (C, D) are user-input OR defaulted from the Falvey
       damage curves for circular-arc offsets of 1/4", 1/2", 1".
    4. Total damage at a station over the hydrograph is
           D_total = integral_0^T  D(Q(t)) dt
       = sum over time increments.

This Python port:
    - fits the sigma(Q) curve,
    - accepts the Falvey default damage coefficients (3 sets: 1/4", 1/2", 1"
      circular-arc offsets), and
    - computes the cumulative damage integral for a user-supplied hydrograph.

Reference:
    Henry T. Falvey, "Cavitation in Chutes and Spillways",
    USBR Engineering Monograph No. 42, 1990, Chapter 7.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


# Default damage coefficients (from Falvey 1990, Table 7.1).
# Format: (C, D) such that D = 10**(C + D*log10(sigma))
# where D is the damage RATE in inches per hour of operation.
# These are the "circular arc" damage curves.
DEFAULT_DAMAGE_COEFFS = {
    "1/4_in": (-3.660, 2.383),    # 1/4-inch offset  (sigma=0.20 => ~1 in/hr)
    "1/2_in": (-4.180, 2.383),    # 1/2-inch offset
    "1_in":   (-4.700, 2.383),    # 1-inch offset
}

# 90-degree offset curves
DEFAULT_90_DEG_COEFFS = {
    "1/4_in": (-3.890, 2.300),
    "1/2_in": (-4.330, 2.300),
    "1_in":   (-4.850, 2.300),
}


@dataclass
class HydrographPoint:
    """One (time, Q) point on the inflow hydrograph."""
    t: float           # hours
    q: float           # cms or cfs (must match input units)


@dataclass
class SigmaQData:
    """One (Q, sigma) calibration point, e.g. from prototype observations."""
    q: float
    sigma: float


@dataclass
class FitResult:
    a: float
    b: float
    """log10(sigma) = a + b * log10(Q)"""
    n_points: int


def fit_sigma_q(points: List[SigmaQData]) -> FitResult:
    """Least-squares fit of log10(sigma) = a + b*log10(Q)."""
    if len(points) < 2:
        raise ValueError("At least 2 points required for a fit")
    x = [math.log10(p.q) for p in points]
    y = [math.log10(p.sigma) for p in points]
    n = len(x)
    sx = sum(x)
    sy = sum(y)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    sxx = sum(xi * xi for xi in x)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        raise ValueError("Degenerate fit (constant Q)")
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return FitResult(a=a, b=b, n_points=n)


def sigma_at_q(q: float, fit: FitResult) -> float:
    """Predict sigma at a given Q using the fitted curve."""
    if q <= 0:
        return float("inf")
    return 10.0 ** (fit.a + fit.b * math.log10(q))


def damage_potential(sigma: float, coeffs: Tuple[float, float]) -> float:
    """Compute damage potential D (inches per hour) for a given sigma.
    
    D = 10**(C + D*log10(sigma))
    
    If sigma is so large that D would round to 0, returns 0.
    If sigma is 0 or negative, returns 0.
    """
    if sigma <= 0:
        return 0.0
    log_d = coeffs[0] + coeffs[1] * math.log10(sigma)
    if log_d < -10:
        return 0.0
    if log_d > 10:
        return 1e10   # saturate at very high damage
    return 10.0 ** log_d


@dataclass
class DamageResult:
    """Total damage at a station for a full hydrograph."""
    fit: FitResult
    sigma_min: float
    sigma_max: float
    damage_curve: str
    total_damage: float            # integrated over the hydrograph
    damage_trace: List[Tuple[float, float, float]] = field(default_factory=list)
    """List of (t, Q, D) at each hydrograph point."""


def total_damage(
    hydrograph: List[HydrographPoint],
    fit: FitResult,
    damage_curve: str = "1/4_in",
    use_90_deg: bool = False,
) -> DamageResult:
    """Compute the cumulative damage for a hydrograph using the fitted sigma-Q curve.
    
    The total damage is the trapezoidal-rule integral of D(Q(t)) over time.
    """
    coeffs = (DEFAULT_90_DEG_COEFFS if use_90_deg else DEFAULT_DAMAGE_COEFFS)[damage_curve]
    if not hydrograph:
        return DamageResult(fit=fit, sigma_min=0, sigma_max=0,
                            damage_curve=damage_curve, total_damage=0.0)
    trace = []
    sigmas = []
    damages = []
    for p in hydrograph:
        s = sigma_at_q(p.q, fit) if p.q > 0 else float("inf")
        d = damage_potential(s, coeffs)
        sigmas.append(s)
        damages.append(d)
        trace.append((p.t, p.q, d))
    # Trapezoidal integration
    total = 0.0
    for i in range(1, len(hydrograph)):
        dt = hydrograph[i].t - hydrograph[i-1].t
        total += 0.5 * (damages[i] + damages[i-1]) * dt
    return DamageResult(
        fit=fit,
        sigma_min=min(sigmas),
        sigma_max=max(sigmas),
        damage_curve=damage_curve,
        total_damage=total,
        damage_trace=trace,
    )


# ============================================================================
# Self-test (round-trip with reference data)
# ============================================================================

if __name__ == "__main__":
    # Synthetic data: a typical spillway sigma-Q relationship
    # sigma = 0.42 * (Q / 100)^-0.30
    pts = [
        SigmaQData(q=100, sigma=0.42),
        SigmaQData(q=200, sigma=0.30),
        SigmaQData(q=500, sigma=0.20),
        SigmaQData(q=1000, sigma=0.15),
    ]
    fit = fit_sigma_q(pts)
    print(f"Fitted log10(sigma) = {fit.a:.3f} + {fit.b:.3f} * log10(Q)")
    
    # Check fit at Q = 100: expected sigma = 0.42
    s = sigma_at_q(100, fit)
    print(f"sigma(100) = {s:.3f} (expected 0.42)")
    
    # Damage at sigma = 0.20 with 1/2-in curve
    d = damage_potential(0.20, DEFAULT_DAMAGE_COEFFS["1/2_in"])
    print(f"D(sigma=0.20, 1/2-in) = {d:.4e} in/hr")
    
    # Hydrograph: triangular, peak Q = 500 at t=6h, duration 12h
    hydro = [
        HydrographPoint(0,  0),
        HydrographPoint(1,  83),
        HydrographPoint(2, 167),
        HydrographPoint(3, 250),
        HydrographPoint(4, 333),
        HydrographPoint(5, 417),
        HydrographPoint(6, 500),
        HydrographPoint(7, 417),
        HydrographPoint(8, 333),
        HydrographPoint(9, 250),
        HydrographPoint(10, 167),
        HydrographPoint(11, 83),
        HydrographPoint(12, 0),
    ]
    res = total_damage(hydro, fit, "1/2_in")
    print(f"Total damage = {res.total_damage:.4e} inches")
    print(f"sigma range: {res.sigma_min:.3f} - {res.sigma_max:.3f}")
    print("DINDX self-test passed.")
