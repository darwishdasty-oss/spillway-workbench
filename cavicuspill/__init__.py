"""
Spillway Workbench (SWB)
=========================

A merged tool combining:
  - **Cavicuspill**: spillway *design* (flood routing -> spillway dimensions
    given Q and damage criteria)
  - **EM-Py**: cavitation *analysis* (spillway dimensions -> water surface
    profile, cavitation index, damage rates)

Both are ports of USBR-era DOS programs to Python 3 / PySide6:
  - Cavicuspill (Abbas A. Hebah, 2004-2006; VB6 -> Python 2024-2026)
  - EM-Py (Henry T. Falvey's "Cavitation Programs" 1987/1990, ported 2026)

The two share an MDI shell, an APP_STATE, a Reports menu, a CLI, and a
PyInstaller-built single-file binary.
"""
__version__ = "1.3.2"

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np
import math
__author__ = "Abbas A. Hebah"
__license__ = "MIT"


# Re-exports from original cavicuspill.py
@dataclass
class ReservoirTable:
    """Elevation (h) -> storage volume (V) lookup, plus interpolation."""
    e: float = 0.0           # initial elevation h_0
    h: np.ndarray = field(default_factory=lambda: np.array([]))
    V: np.ndarray = field(default_factory=lambda: np.array([]))

    def V_at(self, h: float) -> float:
        return float(np.interp(h, self.h, self.V))


def interpolate_reservoir_table(h_in: np.ndarray, V_in: np.ndarray,
                                n2: int) -> np.ndarray:
    """
    Interpolate the input (h, V) table to a finer grid with n2
    subdivisions between each pair of input points.

    Faithful port of the original VB6 `fillDatas` algorithm in
    ReservoirProperties.frm, converted to 0-based Python indexing.

    For n1 input points and n2 subdivisions per interval, the number of
    fine-grid points is:
        M = (n1 - 1) * n2 + 1
    This is the formula used in the original VB6 where the user's n1
    is 1-based and the loop runs n2 times per interval; in 0-based
    Python it is (n1-1) * n2 + 1.

    Parameters
    ----------
    h_in : 1-D array of input elevations (n1 points, strictly increasing)
    V_in : 1-D array of input volumes      (n1 points, strictly increasing)
    n2   : number of subdivisions between each pair of input points

    Returns
    -------
    fine : (M, 2) array of (h, V) points
    """
    if n2 < 1:
        raise ValueError("n2 must be >= 1")
    n1 = len(h_in)
    if len(V_in) != n1:
        raise ValueError("h_in and V_in must have the same length")
    M = (n1 - 1) * n2 + 1
    fine = np.zeros((M, 2))
    cn = 0   # 0-based Python index
    for i in range(n1 - 1):
        h1, h2 = h_in[i], h_in[i + 1]
        v1, v2 = V_in[i], V_in[i + 1]
        incUnit = (h2 - h1) / n2
        j = h1
        for k in range(n2):
            jround = round(j, 3)
            fine[cn, 0] = jround
            fine[cn, 1] = round((jround - h1) * (v2 - v1) / (h2 - h1) + v1, 3)
            cn += 1
            j = j + incUnit
    # Final point: the last input point itself
    fine[cn, 0] = h_in[-1]
    fine[cn, 1] = V_in[-1]
    return fine


# =============================================================================
# 3. INFLOW HYDROGRAPH
# =============================================================================

@dataclass
class InflowHydrograph:
    n: int = 0
    t_h: np.ndarray = field(default_factory=lambda: np.array([]))   # hours
    Q: np.ndarray = field(default_factory=lambda: np.array([]))     # m^3/s


# =============================================================================
# 4. SPILLWAY DATA
# =============================================================================

@dataclass
class SpillwayConfig:
    L_min: float = 70.0
    L_max: float = 80.0
    b:     float = 5.0        # increment
    c:     float = 2.225      # discharge coefficient
    deltaT: float = 2.0       # routing time step, hours


# =============================================================================
# 5. STORAGE-DISCHARGE (G-Q) PRECOMPUTATION
#    (verbatim from SpillWayData.frm.calc in the original VB6 source)
# =============================================================================

def precompute_gq_curves(reservoir: ReservoirTable,
                         cfg: SpillwayConfig) -> list:
    """
    Precompute the (G - Q) storage-outflow curves for every spillway
    length L in [L_min, L_max] stepped by b.

    Faithful port of the original VB6 ``SpillWayDataFrm.calc``:

        num  = (n1 - 1) * (n2 - 1) + n1          # fine-grid points
        lnum = (L_max - L_min) / b + 1           # (+1 if not divisible)
        For each L_i:
            Qn = L_i * C * (hn - h0) ^ 1.5       # weir equation
            Gn = 2 * Vn / (deltaT * 3600) + Qn   # G = 2S/dt + Q

    where ``h0`` is the initial reservoir elevation ``reservoir.e`` and
    ``(hn, Vn)`` run over the interpolated reservoir fine grid
    (``reservoir.h`` / ``reservoir.V``, produced by
    :func:`interpolate_reservoir_table`).

    The ``G`` function is the pulse-method working variable
    ``G = 2S/dt + Q`` (Algorithm_Documentation v12, Module 1):
    ``(2 S2/dt) + Q2 = (I1 + I2) + (2 S1/dt) - Q1``.

    Returns
    -------
    list of (L, Q, G) tuples with 1-D float arrays of equal length,
    one tuple per spillway length (ascending).  The last length is
    capped at ``L_max`` exactly as in the VB6 source.
    """
    if cfg.b <= 0:
        raise ValueError("b must be > 0")
    if cfg.L_max <= cfg.L_min:
        raise ValueError("L_max must be > L_min")
    h0 = float(reservoir.e)
    h_fine = np.asarray(reservoir.h, dtype=float)
    V_fine = np.asarray(reservoir.V, dtype=float)
    if h_fine.size == 0 or h_fine.size != V_fine.size:
        raise ValueError("reservoir fine grid is empty or ragged")

    span = cfg.L_max - cfg.L_min
    n_steps = int(round(span / cfg.b))
    # VB6: lnum = span/b + 1, then Int(lnum)+1 when (Lmax-Lmin) Mod b <> 0.
    if abs(span - n_steps * cfg.b) > 1e-9 * max(1.0, abs(span)):
        lnum = n_steps + 2
    else:
        lnum = n_steps + 1

    curves = []
    for i in range(lnum):
        L = cfg.L_min + i * cfg.b
        if L > cfg.L_max:
            L = cfg.L_max            # VB6 caps the last curve at L_max
        Qn = L * cfg.c * np.maximum(h_fine - h0, 0.0) ** 1.5
        Gn = 2.0 * V_fine / (cfg.deltaT * 3600.0) + Qn
        curves.append((float(L), Qn, Gn))
    return curves


# =============================================================================
# 6. PULSE METHOD FLOOD ROUTING
#    (verbatim from Outflow.frm.calc_JXMO + calc_On in the original VB6 source)
# =============================================================================

def pulse_method_routing(inflow: InflowHydrograph,
                         gq) -> Tuple[np.ndarray, np.ndarray]:
    """
    Route the inflow hydrograph through the reservoir with the Pulse
    (storage-indication) method for one spillway length.

    Faithful port of the original VB6 ``OutflowFrm.calc_JXMO`` together
    with its ``calc_On`` G -> Q interpolation.  The working equation
    (Algorithm_Documentation v12, Module 1) is

        (2 S2/dt) + Q2 = (I1 + I2) + (2 S1/dt) - Q1

    which in the ``G = 2S/dt + Q`` notation of :func:`precompute_gq_curves`
    reads ``G2 = (I1 + I2) + G1 - 2*Q2``.  Per time step the VB6 source
    computes::

        JX(i) = I(i) + I(i-1)              # (I1 + I2)
        rhs   = JX(i) + JX(i-1).G          # + G1
        Q2    = interp(rhs, G-curve, Q-curve)
        JX(i).G = rhs - 2*Q2               # G2 carried to the next step

    with the initial condition ``MO(1) = Q0`` and ``JX(1) = G0`` taken at
    the first fine-grid point (the reservoir crest, where Q0 = 0).

    Parameters
    ----------
    inflow : InflowHydrograph with ``.Q`` of length ``n``.
    gq     : one (L, Q, G) tuple as produced by
             :func:`precompute_gq_curves`.

    Returns
    -------
    (JX, MO) : 1-D float arrays of length ``n``.
        ``MO``  is the routed outflow hydrograph (m^3/s) at the inflow
        time points;  ``JX`` is the working variable ``G = 2S/dt + Q``.

    Note
    ----
    The VB6 ``calc_On`` returns 0 for a right-hand value beyond the end
    of the G table (uninitialized variable).  This port clamps to the
    last tabulated Q (spillway capacity) via ``numpy.interp``, which is
    the physically correct behaviour; inside the tabulated range both
    implementations are identical linear interpolation.
    """
    L, Qg, Gg = gq[0], np.asarray(gq[1], dtype=float), np.asarray(gq[2], dtype=float)
    Q_in = np.asarray(inflow.Q, dtype=float)
    n = Q_in.size
    if n == 0:
        return np.zeros(0), np.zeros(0)
    JX = np.zeros(n, dtype=float)
    MO = np.zeros(n, dtype=float)
    MO[0] = float(Qg[0])          # Q0 at the crest point
    JX[0] = float(Gg[0])          # G0 = 2 S0/dt + Q0
    for i in range(1, n):
        jx_i = Q_in[i] + Q_in[i - 1]                    # (I1 + I2)
        rhs = jx_i + JX[i - 1]                          # + G1
        MO[i] = float(np.interp(rhs, Gg, Qg))           # Q2
        JX[i] = rhs - 2.0 * MO[i]                       # G2
    return JX, MO


# =============================================================================
# 7. WES STANDARD OVERFLOW CREST DESIGN
#    (manuscript Eq. 4 + Table 1; USBR Design of Small Dams, 1987)
# =============================================================================

GRAVITY = 9.80665   # m/s^2

# WES standard crest-shape coefficients for the four standard upstream-face
# slopes (manuscript Table 1, ref. USBR Design of Small Dams, 1987).
# Downstream quadrant:  y/Hd = -K * (x/Hd)^P   (x, y from the crest apex)
# Upstream quadrant: composite circular arcs r1, r2 with offsets a, b.
WES_KP_TABLE = {
    "3V:0H": (0.500, 1.850),   # vertical upstream face
    "3V:1H": (0.516, 1.836),
    "3V:2H": (0.515, 1.810),
    "3V:3H": (0.534, 1.776),
}

WES_COEFFS = {
    "3V:0H": {"a": 0.175, "b": 0.282, "r1": 0.500, "r2": 0.200, "K": 0.500, "P": 1.850},
    "3V:1H": {"a": 0.139, "b": 0.237, "r1": 0.680, "r2": 0.210, "K": 0.516, "P": 1.836},
    "3V:2H": {"a": 0.115, "b": 0.214, "r1": 0.480, "r2": 0.220, "K": 0.515, "P": 1.810},
    "3V:3H": {"a": 0.000, "b": 0.199, "r1": 0.450, "r2": None,  "K": 0.534, "P": 1.776},
}


def wes_design(Q_d: float, L: float, c: float,
               upstream_slope: str = "3V:0H") -> dict:
    """
    Size a WES standard overflow crest for the design discharge ``Q_d``.

    Inverts the weir relation ``Q = c * L * H_e**1.5`` (manuscript
    Eq. 4 basis) for the effective head ``H_e``, then splits it into the
    design head ``H_d`` and the velocity head of the crest-control
    section mean velocity ``V_1 = Q_d / (L * H_e)``:

        H_e = (Q_d / (c * L)) ** (2/3)
        V_1 = Q_d / (L * H_e)
        H_d = H_e - V_1**2 / (2 g)

    Also reports the design checks of the manuscript: the minimum crest
    height above the apron ``1.33 * H_d`` required for complete crest
    development, and the ratio ``H_e / H_d`` (a WES discharge
    coefficient is a maximum when ``H_e / H_d`` is close to 1).

    Returns a dict with keys ``H_e, H_d, V_1, upstream_slope, coeffs,
    P_Hd_min, H_e_over_Hd`` (``coeffs`` = the WES_COEFFS entry for the
    selected slope).
    """
    if upstream_slope not in WES_COEFFS:
        raise ValueError(f"unknown upstream slope '{upstream_slope}'; "
                         f"expected one of {sorted(WES_COEFFS)}")
    if Q_d <= 0.0 or L <= 0.0 or c <= 0.0:
        raise ValueError("Q_d, L and c must be positive")
    H_e = (Q_d / (c * L)) ** (2.0 / 3.0)
    V_1 = Q_d / (L * H_e)
    H_d = H_e - V_1 * V_1 / (2.0 * GRAVITY)
    return {
        "H_e": H_e,
        "H_d": H_d,
        "V_1": V_1,
        "upstream_slope": upstream_slope,
        "coeffs": dict(WES_COEFFS[upstream_slope]),
        "P_Hd_min": 1.33 * H_d,
        "H_e_over_Hd": H_e / H_d,
    }


# =============================================================================
# 8. WATER SURFACE PROFILE BY THE STANDARD STEP METHOD
#    (manuscript Eq. 5-6; GVF energy balance with averaged Manning friction)
# =============================================================================

def standard_step(Q: float, b: float, n_manning: float, S0: float,
                  y0: float, dx: float, n_steps: int) -> Tuple[np.ndarray, ...]:
    """
    Compute the water-surface profile of a rectangular chute by the
    Standard Step Method (manuscript Section 2.2, Eqs. 5-6).

    Between successive stations spaced ``dx`` apart the energy equation

        E(y2) + z2 + hf = E(y1) + z1 ,   hf = 0.5 (Sf1 + Sf2) dx

    is solved for the unknown downstream depth, with Manning friction
    ``Sf = n^2 V^2 / R^(4/3)`` and ``R = b y / (b + 2 y)``.  The implicit
    equation is solved by bisection on the correct branch of the
    specific-energy curve (supercritical below critical depth,
    subcritical above) to a depth tolerance of 1 mm, per the manuscript
    tolerance statement.

    Parameters: ``Q`` discharge (m^3/s), ``b`` bottom width (m),
    ``n_manning`` Manning coefficient, ``S0`` bed slope (m/m), ``y0``
    boundary depth at the upstream station (m), ``dx`` station spacing
    (m), ``n_steps`` number of reaches.

    Returns ``(x, y, V)``: 1-D arrays of length ``n_steps + 1`` with the
    station coordinate measured downstream from the crest (m), the flow
    depth (m) and the mean velocity (m/s).
    """
    if Q <= 0 or b <= 0 or n_manning <= 0 or dx <= 0:
        raise ValueError("Q, b, n and dx must be positive")
    if y0 <= 0:
        raise ValueError("y0 must be positive")
    n_st = int(n_steps)
    if n_st < 1:
        raise ValueError("n_steps must be >= 1")
    g = GRAVITY

    def _vel(yv):
        return Q / (b * yv)

    def _hyd_radius(yv):
        return b * yv / (b + 2.0 * yv)

    def _fric(yv):
        v = _vel(yv)
        return n_manning ** 2 * v * v / _hyd_radius(yv) ** (4.0 / 3.0)

    def _energy(yv):
        return yv + _vel(yv) ** 2 / (2.0 * g)

    x = np.arange(n_st + 1) * float(dx)
    y = np.zeros(n_st + 1, dtype=float)
    V = np.zeros(n_st + 1, dtype=float)
    y[0] = float(y0)
    V[0] = _vel(y[0])

    # Critical depth of a rectangular section: yc = (Q^2 / (g b^2))^(1/3)
    yc = (Q * Q / (g * b * b)) ** (1.0 / 3.0)
    total_length = x[-1]
    depth_tol = 1.0e-8         # solved well below the manuscript 1 mm tolerance

    for i in range(n_st):
        z1 = (total_length - x[i]) * S0
        z2 = (total_length - x[i + 1]) * S0
        E1 = _energy(y[i])
        Sf1 = _fric(y[i])

        def _residual(y2):
            return (_energy(y2) + z2 + 0.5 * (Sf1 + _fric(y2)) * dx
                    - (E1 + z1))

        if y[i] <= yc:      # supercritical branch (steep chute)
            lo, hi = 1.0e-4 * yc, yc * (1.0 - 1.0e-9)
            f_lo, f_hi = _residual(lo), _residual(hi)
        else:               # subcritical branch
            lo, hi = yc * (1.0 + 1.0e-9), 1.0e3 * yc
            f_lo, f_hi = _residual(lo), _residual(hi)
        k_expand = 0
        while f_lo * f_hi > 0.0 and k_expand < 60:
            # widen the bracket until the residual changes sign
            if y[i] <= yc:
                lo *= 0.5
                hi = yc * (1.0 - 1.0e-9)
            else:
                hi *= 2.0
                lo = yc * (1.0 + 1.0e-9)
            f_lo, f_hi = _residual(lo), _residual(hi)
            k_expand += 1
        if f_lo * f_hi > 0.0:
            raise ValueError(
                f"standard_step: no energy-balance solution at station {i + 1}; "
                "check S0, dx and the boundary depth.")
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            f_mid = _residual(mid)
            if abs(hi - lo) < depth_tol:
                break
            if f_lo * f_mid <= 0.0:
                hi, f_hi = mid, f_mid
            else:
                lo, f_lo = mid, f_mid
        y[i + 1] = 0.5 * (lo + hi)
        V[i + 1] = _vel(y[i + 1])
    return x, y, V


# =============================================================================
# 9. TEMPERATURE-DEPENDENT WATER PROPERTIES
#    (manuscript Table 2; saturated-water data consistent with IAPWS)
# =============================================================================

# (T [degC], rho [kg/m^3], p_v [kPa], nu [1e-6 m^2/s]) -- manuscript Table 2
WATER_PROPS_TABLE = [
    (0.0,   999.868,  0.61, 1.787),
    (5.0,   999.992,  0.87, 1.519),
    (10.0,  999.726,  1.23, 1.307),
    (15.0,  999.125,  1.70, 1.140),
    (20.0,  998.228,  2.33, 1.004),
    (25.0,  997.069,  3.16, 0.893),
    (30.0,  995.671,  4.23, 0.801),
    (40.0,  992.238,  7.38, 0.658),
    (50.0,  988.052, 12.30, 0.553),
    (60.0,  983.200, 19.90, 0.475),
    (70.0,  977.770, 31.10, 0.413),
    (80.0,  971.800, 47.30, 0.365),
    (90.0,  965.310, 70.10, 0.326),
    (100.0, 958.360, 101.30, 0.294),
]


def water_properties(T: float) -> Tuple[float, float, float]:
    """
    Return ``(rho [kg/m^3], p_v [Pa], nu [m^2/s])`` at temperature ``T``
    [degC] by linear interpolation of the manuscript Table 2, clipped to
    the tabulated range 0-100 degC.
    """
    Ts = [row[0] for row in WATER_PROPS_TABLE]
    Tc = min(max(float(T), Ts[0]), Ts[-1])
    rho = float(np.interp(Tc, Ts, [r[1] for r in WATER_PROPS_TABLE]))
    pv = float(np.interp(Tc, Ts, [r[2] for r in WATER_PROPS_TABLE])) * 1000.0
    nu = float(np.interp(Tc, Ts, [r[3] for r in WATER_PROPS_TABLE])) * 1.0e-6
    return rho, pv, nu


# =============================================================================
# 10. CAVITATION INDICES
#     (manuscript Eq. 1; EM-42 Eq. 2.10 + fig. 2-5; manuscript Eq. 10)
# =============================================================================

def cavitation_index_flow(p0: float, V: float, T: float) -> float:
    """
    Flow-surface cavitation index (manuscript Eq. 1):

        sigma = (p0 - p_v) / (0.5 * rho * V^2)

    ``p0`` is the local absolute reference pressure [Pa], ``V`` the mean
    reference velocity [m/s] and ``T`` the water temperature [degC]
    (density and vapour pressure from :func:`water_properties`).
    """
    if V <= 0:
        raise ValueError("V must be positive")
    rho, pv, _nu = water_properties(T)
    return (p0 - pv) / (0.5 * rho * V * V)


# Isolated-irregularity incipient-cavitation coefficients, Falvey (1990,
# EM-42) fig. 2-5:  sigma_r = C (H/delta)^a (V_b delta / nu)^b   (Eq. 2.10)
ROUGHNESS_CLASSES = {
    "triangles":     {"a": 0.361, "b": 0.196, "C": 0.152},     # Holl, 1960
    "circular_arcs": {"a": 0.344, "b": 0.267, "C": 0.041},     # Holl, 1960
    "hemispheres":   {"a": 0.439, "b": 0.298, "C": 0.0108},    # Benson, 1966
    "cones":         {"a": 0.632, "b": 0.451, "C": 0.00328},   # Benson, 1966
    "cylinders":     {"a": 0.737, "b": 0.550, "C": 0.00117},   # Benson, 1966
    "slots":         {"a": 0.041, "b": 0.510, "C": 0.000314},  # Bohn, 1972
}


def cavitation_index_singular_roughness(V_b: float, H: float, delta: float,
                                        T: float,
                                        roughness_class: str = "triangles"
                                        ) -> float:
    """
    Incipient cavitation index for an isolated roughness element
    (EM-42 Eq. 2.10; manuscript Eq. 9 basis):

        sigma_r = C (H / delta)^a (V_b * delta / nu)^b

    ``V_b`` is the velocity at the edge of the boundary layer [m/s],
    ``H`` the element height [m], ``delta`` the boundary-layer
    thickness [m] and ``T`` the water temperature [degC].  The
    coefficient sets ``(C, a, b)`` for the six EM-42 classes are in
    :data:`ROUGHNESS_CLASSES`; the default class ``triangles``
    (triangular elements facing into the flow) reproduces the EM-42
    worked example ``sigma_r = 0.565`` cited in the manuscript
    verification section.
    """
    if H <= 0 or delta <= 0 or V_b <= 0:
        raise ValueError("V_b, H and delta must be positive")
    if roughness_class not in ROUGHNESS_CLASSES:
        raise ValueError(f"unknown roughness class '{roughness_class}'; "
                         f"expected one of {sorted(ROUGHNESS_CLASSES)}")
    _rho, _pv, nu = water_properties(T)
    co = ROUGHNESS_CLASSES[roughness_class]
    Re_delta = V_b * delta / nu
    return co["C"] * (H / delta) ** co["a"] * Re_delta ** co["b"]


def cavitation_index_uniform(V: float, R: float, Sf: float) -> float:
    """
    Incipient cavitation index for uniformly rough surfaces
    (manuscript Eq. 10):

        sigma_i = 16 Cf = 4 f = 32 g R Sf / V^2

    ``V`` the mean velocity [m/s], ``R`` the hydraulic radius [m] and
    ``Sf`` the friction slope (Manning, manuscript Eq. 6) at the local
    conditions.
    """
    if V <= 0:
        raise ValueError("V must be positive")
    return 32.0 * GRAVITY * R * Sf / (V * V)

