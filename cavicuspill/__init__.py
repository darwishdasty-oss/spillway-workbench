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
__version__ = "1.0.0"

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

