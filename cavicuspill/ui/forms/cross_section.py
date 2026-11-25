"""
ui/forms/cross_section.py - Unified port of all 9 cross-section forms.

The original VB6 has 9 separate .frm files (Rectangular, Tropizodal,
Circular, EggShape, HorseShoe, ModifiedHorseShoe, RectangularCorner,
Trangular, TrangularCorner), each with 1-2 dimensional inputs and an
OK button that sets a flag in the global CrossSections variable.

This PySide6 port consolidates them into a single factory function
`make_cross_section_dialog(section_type)` that returns a QMdiSubWindow
with the appropriate inputs, geometric property computations, a
matplotlib cross-section drawing, and APP_STATE updates.

The 9 section types and the geometry used in v1.3.2:

| # | Section        | Inputs  | A(y), P(y), T(y) source                        |
|---|----------------|---------|------------------------------------------------|
| 1 | Rectangular    | b       | closed form                                     |
| 2 | Trapezoidal    | b, Z    | closed form                                     |
| 3 | Circular       | D       | circular-segment closed form                    |
| 4 | Egg-shaped     | D       | Baldwin-Latham Form-1 egg (Enfinger 2024);      |
|   |                |         | exact tangent-circle construction, A/P closed   |
| 5 | HorseShoe      | D       | USBR standard horseshoe (Merkley 2005): four    |
|   |                |         | tangent circles, exact A/P closed form          |
| 6 | Modified HS    | b       | rectangle + semicircular crown (height = b)     |
| 7 | Rect. corner   | b, r    | rectangle with rounded invert corners, exact    |
| 8 | Triangular     | Z       | closed form                                     |
| 9 | Tri. corner    | Z, r    | V-section with rounded invert, exact            |

v1.3.2 replaces the v1.3.0 placeholder relations with the exact
constructions above and draws every section from its true outline
(the same width function that produces A and P), so the drawing and
the numbers can never disagree again.

References
----------
Enfinger, K. L. (2024). "Geometric and Hydraulic Elements of Egg-Shaped
Sewers", ADS Environmental Services — Baldwin-Latham Form 1 geometry
(invert circle D1 = DT/2, side circles D2 = 3*DT, arch circle D3 = DT,
DV = 1.5*DT) with validated area/perimeter tables.
Merkley, G. P. (2005). "Standard horseshoe cross section geometry",
Agricultural Water Management 71, 121-134 — four-circle construction
(three circles of radius H, one of radius H/2; width = height = H).

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations
import os, sys
import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cavicuspill as cav  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from cavicuspill.ui import mdi_main as _mdi_main  # noqa: E402  (merged shell / package)
except ImportError:  # standalone run (sys.path hack above)
    import mdi_main as _mdi_main  # noqa: E402
APP_STATE = _mdi_main.APP_STATE
from charts.matplotlib_widget import MplCanvas  # noqa: E402


# =============================================================================
#  SECTION SPECS  (labels mirror the original VB6 captions; defaults are
#  type-appropriate and consistent with the flow depth y)
# =============================================================================
@dataclass
class SectionSpec:
    name: str
    original_form: str   # original VB6 file name
    inputs: List[Tuple[str, str, float]]   # [(label, unit, default)]
    menu_label: str      # label in the Cross-Sections menu


SECTION_SPECS = [
    SectionSpec("Rectangular",         "Rectangular",        [("b (Width)", "m", 5.0)],
                "&Rectangular"),
    SectionSpec("Trapezoidal",         "Tropizodal",         [("b (Width)", "m", 5.0),
                                                                ("Z (Side slope)", "",  1.0)],
                "&Trapezoidal"),
    SectionSpec("Circular",            "Circular",           [("D (Diameter)", "m", 5.0)],
                "&Circular"),
    SectionSpec("Egg-shaped",          "EggShape",           [("D (Height)", "m", 3.0)],
                "&Egg-shaped"),
    SectionSpec("Horseshoe",           "HorseShoe",          [("D (Diameter)", "m", 5.0)],
                "&Horseshoe"),
    SectionSpec("Modified horseshoe",  "ModifiedHorseShoe",  [("b (Width)", "m", 5.0)],
                "&Modified horseshoe"),
    SectionSpec("Rectangular corner",  "RectangularCorner",  [("b (Width)", "m", 5.0),
                                                                ("r (Radius)", "m", 0.5)],
                "Rectangular &corner"),
    SectionSpec("Triangular",          "Trangular",          [("Z (Side slope)", "", 1.0)],
                "&Triangular"),
    SectionSpec("Triangular corner",   "TrangularCorner",    [("Z (Side slope)", "", 1.0),
                                                                ("r (Radius)", "m", 0.5)],
                "Triangular &corner"),
]


# =============================================================================
#  CLOSED-FORM HELPERS
# =============================================================================
def _G(r: float, x: float) -> float:
    """G(x) = (x/2)*sqrt(r^2-x^2) + (r^2/2)*asin(x/r), so that
    2*[G(r) - G(c-h)] = area of both symmetric circle chords from the
    circle bottom up to height h (center height c, radius r)."""
    x = max(-r, min(r, x))
    return 0.5 * x * math.sqrt(max(0.0, r * r - x * x)) + 0.5 * r * r * math.asin(x / r)


def _arc_t(r: float, c: float, h: float) -> float:
    """Central angle (from the downward vertical) of the circle points at
    height h; the full symmetric arc from the bottom up to h spans 2*t."""
    cos_t = (c - h) / r
    return math.acos(max(-1.0, min(1.0, cos_t)))


# =============================================================================
#  GEOMETRY FUNCTIONS  (y = flow depth from the invert; dims from the form)
#  Each returns (Area A, wetted perimeter P, top width T).
# =============================================================================
def geom_rectangular(y, dims, **_):
    b = dims["b (Width)"]
    if y <= 0:
        return 0, 0, 0
    A = b * y
    P = b + 2 * y
    T = b
    return A, P, T

def geom_trapezoidal(y, dims, **_):
    b = dims["b (Width)"]
    Z = dims["Z (Side slope)"]
    if y <= 0:
        return 0, 0, 0
    A = (b + Z * y) * y
    P = b + 2 * y * math.sqrt(1 + Z * Z)
    T = b + 2 * Z * y
    return A, P, T

def geom_circular(y, dims, **_):
    D = dims["D (Diameter)"]
    R = D / 2.0
    if y <= 0:
        return 0, 0, 0
    if y >= D:
        # Full pipe: A = pi*R^2, P = pi*D, T = 0
        return math.pi * R * R, math.pi * D, 0.0
    ratio = (R - y) / R
    ratio = max(-1.0, min(1.0, ratio))
    theta = math.acos(ratio)
    A = R * R * (theta - math.sin(theta) * math.cos(theta))
    P = 2 * R * theta
    T = 2 * R * math.sin(theta)
    return A, P, T

def geom_egg_shape(y, dims, **_):
    """Baldwin-Latham Form-1 egg (Enfinger 2024).

    Input D is the egg HEIGHT (the VB6 caption 'D (Height)'), so the
    transverse diameter DT = D / 1.5.  Construction (units of DT):
      invert circle  r=0.25 centered (0, 0.25), used to h = 0.1
      side circles   r=1.5  centered (+-1, 1)  (crossover arcs)
      arch circle    r=0.5  centered (0, 1), crown at h = 1.5
    All junctions are exact tangencies (3-4-5 triangle).
    """
    D = dims["D (Height)"]
    DT = D / 1.5
    crown = 1.5 * DT
    if y <= 0:
        return 0, 0, 0
    if y > crown:
        raise ValueError(
            f"flow depth y = {y:g} m exceeds the egg crown height {crown:g} m")
    r_i, c_i = 0.25 * DT, 0.25 * DT          # invert circle
    r_s, x_s, c_s = 1.5 * DT, DT, DT         # side circles (half-offset, height)
    r_c, c_c = 0.5 * DT, DT                  # arch circle
    h1 = 0.1 * DT                            # invert -> side tangency height
    h2 = DT                                  # side -> arch tangency (spring line)
    hh = min(y, crown)
    # --- wetted area (closed form through the G function) ---
    if hh <= h1:
        A = 2.0 * (_G(r_i, c_i) - _G(r_i, c_i - hh))
        P = 2.0 * r_i * _arc_t(r_i, c_i, hh)
    elif hh <= h2:
        A = (2.0 * (_G(r_i, c_i) - _G(r_i, c_i - h1))
             + 2.0 * (_G(r_s, c_s - h1) - _G(r_s, c_s - hh))
             - 2.0 * x_s * (hh - h1))
        P = (2.0 * r_i * _arc_t(r_i, c_i, h1)
             + 2.0 * r_s * (_arc_t(r_s, c_s, hh) - _arc_t(r_s, c_s, h1)))
    else:
        A = (2.0 * (_G(r_i, c_i) - _G(r_i, c_i - h1))
             + 2.0 * (_G(r_s, c_s - h1) - _G(r_s, c_s - h2))
             - 2.0 * x_s * (h2 - h1)
             + 2.0 * (_G(r_c, c_c - h2) - _G(r_c, c_c - hh)))
        P = (2.0 * r_i * _arc_t(r_i, c_i, h1)
             + 2.0 * r_s * (_arc_t(r_s, c_s, h2) - _arc_t(r_s, c_s, h1))
             + 2.0 * r_c * (_arc_t(r_c, c_c, hh) - math.pi / 2.0))
    T = width_egg(hh, dims)
    return A, P, T

def geom_horseshoe(y, dims, **_):
    """USBR standard horseshoe (Merkley 2005).

    Input D is the section height H (the VB6 caption 'D (Diameter)');
    max width = H at half height.  Construction (units of H):
      invert arc   r=1   centered (0, 1)      used to h1 = (3-sqrt(7))/4
      side circles r=1   centered (+-0.5, 0.5) (crossover arcs)
      crown circle r=0.5 centered (0, 0.5),   crown at h = 1
    """
    D = dims["D (Diameter)"]
    crown = D
    if y <= 0:
        return 0, 0, 0
    if y > crown:
        raise ValueError(
            f"flow depth y = {y:g} m exceeds the horseshoe crown height {crown:g} m")
    r_i, c_i = D, D                          # invert arc (radius = H!)
    r_s, x_s, c_s = D, 0.5 * D, 0.5 * D      # side circles
    r_c, c_c = 0.5 * D, 0.5 * D              # crown circle
    h1 = (3.0 - math.sqrt(7.0)) / 4.0 * D    # invert -> side intersection
    h2 = 0.5 * D                             # side -> crown spring line
    hh = y
    if hh <= h1:
        A = 2.0 * (_G(r_i, c_i) - _G(r_i, c_i - hh))
        P = 2.0 * r_i * _arc_t(r_i, c_i, hh)
    elif hh <= h2:
        A = (2.0 * (_G(r_i, c_i) - _G(r_i, c_i - h1))
             + 2.0 * (_G(r_s, c_s - h1) - _G(r_s, c_s - hh))
             - 2.0 * x_s * (hh - h1))
        P = (2.0 * r_i * _arc_t(r_i, c_i, h1)
             + 2.0 * r_s * (_arc_t(r_s, c_s, hh) - _arc_t(r_s, c_s, h1)))
    else:
        A = (2.0 * (_G(r_i, c_i) - _G(r_i, c_i - h1))
             + 2.0 * (_G(r_s, c_s - h1) - _G(r_s, c_s - h2))
             - 2.0 * x_s * (h2 - h1)
             + 2.0 * (_G(r_c, c_c - h2) - _G(r_c, c_c - hh)))
        P = (2.0 * r_i * _arc_t(r_i, c_i, h1)
             + 2.0 * r_s * (_arc_t(r_s, c_s, h2) - _arc_t(r_s, c_s, h1))
             + 2.0 * r_c * (_arc_t(r_c, c_c, hh) - math.pi / 2.0))
    T = width_horseshoe(hh, dims)
    return A, P, T

def geom_modified_horseshoe(y, dims, **_):
    """Modified horseshoe: flat bottom b, vertical walls to b/2, then a
    semicircular crown of radius b/2 (total height b)."""
    b = dims["b (Width)"]
    R = b / 2.0
    crown = b
    if y <= 0:
        return 0, 0, 0
    if y > crown:
        raise ValueError(
            f"flow depth y = {y:g} m exceeds the modified-horseshoe crown "
            f"height {crown:g} m")
    hh = y
    if hh <= R:
        A = b * hh
        P = b + 2.0 * hh
    else:
        # rectangle part + circular segment of height x above the spring line
        x = hh - R
        A = b * R + x * math.sqrt(max(0.0, R * R - x * x)) \
            + R * R * math.asin(min(1.0, x / R))
        arc = 2.0 * R * (math.acos(max(-1.0, min(1.0, -x / R))) - math.pi / 2.0)
        P = b + 2.0 * R + arc
    T = width_modified_horseshoe(hh, dims)
    return A, P, T

def geom_rectangular_corner(y, dims, **_):
    """Rectangle of width b with the two invert corners rounded (radius r)."""
    b = dims["b (Width)"]
    r = dims["r (Radius)"]
    if y <= 0:
        return 0, 0, 0
    if r >= b / 2.0:
        raise ValueError("corner radius r must be smaller than b/2")
    if y <= r:
        A = (b - 2.0 * r) * y + 2.0 * (_G(r, r) - _G(r, r - y))
        P = (b - 2.0 * r) + 2.0 * r * _arc_t(r, r, y)
    else:
        A = ((b - 2.0 * r) * r + math.pi * r * r / 2.0
             + b * (y - r))
        P = (b - 2.0 * r) + 2.0 * (y - r) + math.pi * r
    T = width_rect_corner(y, dims)
    return A, P, T

def geom_triangular(y, dims, **_):
    Z = dims["Z (Side slope)"]
    if y <= 0:
        return 0, 0, 0
    A = Z * y * y
    P = 2 * y * math.sqrt(1 + Z * Z)
    T = 2 * Z * y
    return A, P, T

def geom_triangular_corner(y, dims, **_):
    """V-section (side slope Z) with the invert vertex replaced by a tangent
    rounding circle of radius r.

    The rounding circle (center on the axis at height yc = r*sqrt(1+Z^2)/Z
    above the original vertex) is tangent to both sides; the section invert
    is the bottom of that circle, and flow depth y is measured from it.
    As r -> 0 the section (and its properties) converge to the plain
    triangular section.
    """
    Z = dims["Z (Side slope)"]
    r = dims["r (Radius)"]
    if y <= 0:
        return 0, 0, 0
    if Z <= 0:
        raise ValueError("side slope Z must be positive")
    sq = math.sqrt(1.0 + Z * Z)
    yc = r * sq / Z                 # circle center above the V vertex
    h0 = yc - r                     # section invert (circle bottom)
    h_t = yc - r * Z / sq           # tangency height on the sides
    hh = h0 + y                     # absolute water-surface height
    if hh <= h_t:
        A = 2.0 * (_G(r, yc - h0) - _G(r, yc - hh))
        P = 2.0 * r * _arc_t(r, yc, hh)
    else:
        A = (2.0 * (_G(r, yc - h0) - _G(r, yc - h_t))
             + Z * (hh * hh - h_t * h_t))
        P = (2.0 * r * _arc_t(r, yc, h_t)
             + 2.0 * (hh - h_t) * sq)
    T = width_tri_corner(hh, dims)
    return A, P, T


# =============================================================================
#  WIDTH FUNCTIONS  (full section width at height h above the invert;
#  used for the top width AND to draw the true outline)
# =============================================================================
def width_rect(h, dims):
    b = dims["b (Width)"]
    return b

def width_trap(h, dims):
    b = dims["b (Width)"]
    Z = dims["Z (Side slope)"]
    return b + 2.0 * Z * h

def width_circular(h, dims):
    D = dims["D (Diameter)"]
    R = D / 2.0
    if h >= D:
        return 0.0
    return 2.0 * math.sqrt(max(0.0, R * R - (R - h) ** 2))

def width_egg(h, dims):
    DT = dims["D (Height)"] / 1.5
    u = h / DT
    if u <= 0.1:
        return 2.0 * math.sqrt(max(0.0, 0.25 ** 2 - (0.25 - u) ** 2)) * DT
    if u <= 1.0:
        return 2.0 * (math.sqrt(max(0.0, 1.5 ** 2 - (1.0 - u) ** 2)) - 1.0) * DT
    return 2.0 * math.sqrt(max(0.0, 0.5 ** 2 - (1.0 - u) ** 2)) * DT

def width_horseshoe(h, dims):
    D = dims["D (Diameter)"]
    u = h / D
    h1 = (3.0 - math.sqrt(7.0)) / 4.0
    if u <= h1:
        return 2.0 * math.sqrt(max(0.0, u * (2.0 - u))) * D
    if u <= 0.5:
        return 2.0 * (math.sqrt(max(0.0, 1.0 - (u - 0.5) ** 2)) - 0.5) * D
    return 2.0 * math.sqrt(max(0.0, 0.25 - (u - 0.5) ** 2)) * D

def width_modified_horseshoe(h, dims):
    b = dims["b (Width)"]
    R = b / 2.0
    if h <= R:
        return b
    return 2.0 * math.sqrt(max(0.0, R * R - (h - R) ** 2))

def width_rect_corner(h, dims):
    b = dims["b (Width)"]
    r = dims["r (Radius)"]
    if h <= r:
        return (b - 2.0 * r) + 2.0 * math.sqrt(max(0.0, 2.0 * r * h - h * h))
    return b

def width_tri(h, dims):
    Z = dims["Z (Side slope)"]
    return 2.0 * Z * h

def width_tri_corner(h, dims):
    """h here is the ABSOLUTE height above the original V vertex."""
    Z = dims["Z (Side slope)"]
    r = dims["r (Radius)"]
    sq = math.sqrt(1.0 + Z * Z)
    yc = r * sq / Z
    h_t = yc - r * Z / sq
    if h <= h_t:
        return 2.0 * math.sqrt(max(0.0, r * r - (yc - h) ** 2))
    return 2.0 * Z * h

def crown_tri_corner(dims):
    """The rounding-circle bottom sits above the vertex; exposed depth from
    the invert is unbounded, but drawing needs the offset."""
    Z = dims["Z (Side slope)"]
    r = dims["r (Radius)"]
    return r * math.sqrt(1.0 + Z * Z) / Z - r   # invert offset (h0)


GEOM_FN = {
    "Rectangular":         geom_rectangular,
    "Trapezoidal":         geom_trapezoidal,
    "Circular":            geom_circular,
    "Egg-shaped":          geom_egg_shape,
    "Horseshoe":           geom_horseshoe,
    "Modified horseshoe":  geom_modified_horseshoe,
    "Rectangular corner":  geom_rectangular_corner,
    "Triangular":          geom_triangular,
    "Triangular corner":   geom_triangular_corner,
}

WIDTH_FN = {
    "Rectangular":         width_rect,
    "Trapezoidal":         width_trap,
    "Circular":            width_circular,
    "Egg-shaped":          width_egg,
    "Horseshoe":           width_horseshoe,
    "Modified horseshoe":  width_modified_horseshoe,
    "Rectangular corner":  width_rect_corner,
    "Triangular":          width_tri,
    "Triangular corner":   width_tri_corner,
}

# Crown height (max flow depth); None = open top (unbounded)
CROWN_FN = {
    "Rectangular":         None,
    "Trapezoidal":         None,
    "Circular":            lambda d: d["D (Diameter)"],
    "Egg-shaped":          lambda d: d["D (Height)"],
    "Horseshoe":           lambda d: d["D (Diameter)"],
    "Modified horseshoe":  lambda d: d["b (Width)"],
    "Rectangular corner":  None,
    "Triangular":          None,
    "Triangular corner":   None,
}

# Heights where the outline changes character (for smooth drawing samples)
BREAK_FN = {
    "Rectangular":         lambda d: [],
    "Trapezoidal":         lambda d: [],
    "Circular":            lambda d: [d["D (Diameter)"] / 2.0],
    "Egg-shaped":          lambda d: [0.1 * d["D (Height)"] / 1.5,
                                      d["D (Height)"] / 1.5],
    "Horseshoe":           lambda d: [(3.0 - math.sqrt(7.0)) / 4.0 * d["D (Diameter)"],
                                      0.5 * d["D (Diameter)"]],
    "Modified horseshoe":  lambda d: [0.5 * d["b (Width)"]],
    "Rectangular corner":  lambda d: [d["r (Radius)"]],
    "Triangular":          lambda d: [],
    "Triangular corner":   lambda d: [],
}


# =============================================================================
#  THE UNIFIED DIALOG FACTORY
# =============================================================================
class CrossSectionDialog(QtWidgets.QMdiSubWindow):
    """One dialog that works for all 9 section types, driven by SectionSpec."""

    def __init__(self, spec: SectionSpec, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.spec = spec
        self.setWindowTitle(spec.name)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(720, 540)

        w = QtWidgets.QWidget(self)
        self.setWidget(w)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # ----- Header -----
        hdr = QtWidgets.QLabel(
            f"<b style='color:#1A3A6C; font-size:13pt'>{spec.name} cross-section</b><br>"
            f"<span style='color:#666; font-style:italic; font-size:9pt'>"
            f"Port of <code>{spec.original_form}.frm</code> in the original 2005 "
            f"Visual Basic 6.0 workbench. Enter the cross-section dimensions and a "
            f"flow depth to compute the geometric properties (area A, wetted "
            f"perimeter P, hydraulic radius R<sub>h</sub>, top width T). "
            f"Click <b>OK</b> to commit the active section type to APP_STATE."
            f"</span>")
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # ----- Inputs -----
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        self.txt: dict = {}
        for i, (label, unit, default) in enumerate(spec.inputs):
            row, col = i // 2, i % 2
            edit = QtWidgets.QLineEdit(f"{default:g}")
            edit.setMaximumWidth(110)
            edit.setToolTip(label)
            self.txt[label] = edit
            row_w = QtWidgets.QHBoxLayout()
            row_w.addWidget(edit)
            row_w.addWidget(QtWidgets.QLabel(f"<span style='color:#888'>{unit}</span>"))
            row_w.addStretch(1)
            form.addWidget(QtWidgets.QLabel(label), row, col * 2)
            form.addLayout(row_w, row, col * 2 + 1)
        # Flow depth y (always present); default is type-aware: 60% of the
        # crown height for closed sections, 3.0 m for open channels
        crown_fn = CROWN_FN[spec.name]
        y_default = 0.6 * crown_fn({label: default
                                    for label, _, default in spec.inputs}) \
            if crown_fn is not None else 3.0
        self.txt["y (Flow depth)"] = QtWidgets.QLineEdit(f"{y_default:g}")
        self.txt["y (Flow depth)"].setMaximumWidth(110)
        self.txt["y (Flow depth)"].setToolTip("Flow depth y (from the invert)")
        row_y = QtWidgets.QHBoxLayout()
        row_y.addWidget(self.txt["y (Flow depth)"])
        row_y.addWidget(QtWidgets.QLabel("<span style='color:#888'>m</span>"))
        row_y.addStretch(1)
        last_row = (len(spec.inputs) + 1) // 2
        form.addWidget(QtWidgets.QLabel("y (Flow depth)"), last_row, 0)
        form.addLayout(row_y, last_row, 1)
        v.addLayout(form)

        # ----- Run button -----
        row = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("Compute properties")
        self.btn_run.clicked.connect(self._compute_and_draw)
        row.addWidget(self.btn_run)
        row.addStretch(1)
        v.addLayout(row)

        # ----- Chart -----
        self.canvas = MplCanvas(6.5, 3.5, dpi=100)
        v.addWidget(self.canvas, 1)

        # ----- Status -----
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#444; font-size:8.5pt; font-style:italic;")
        v.addWidget(self.lbl_status)

        # ----- OK / Cancel -----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QtWidgets.QPushButton("&Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_ok = QtWidgets.QPushButton("&OK")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.on_ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        v.addLayout(btn_row)

        # Initial compute
        self._compute_and_draw()

    def _read_inputs(self):
        try:
            dims = {label: float(self.txt[label].text())
                    for label, _, _ in self.spec.inputs}
            y = float(self.txt["y (Flow depth)"].text())
        except ValueError as e:
            self.lbl_status.setText(f"<span style='color:#B8500A'>Invalid: {e}</span>")
            return None
        if any(v <= 0 for v in dims.values()) or y <= 0:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Invalid: all values must be positive</span>")
            return None
        return dims, y

    def _compute_and_draw(self):
        inp = self._read_inputs()
        if inp is None:
            return
        dims, y = inp
        geom = GEOM_FN[self.spec.name]
        try:
            A, P, T = geom(y=y, dims=dims)
        except Exception as e:
            self.lbl_status.setText(f"<span style='color:#B8500A'>Computation error: {e}</span>")
            return
        if A <= 0 or P <= 0:
            self.lbl_status.setText(
                "<span style='color:#B8500A'>Computed A or P is zero; check inputs</span>")
            return
        R_h = A / P
        self._last = (dims, y, A, P, T, R_h)

        # Draw the cross-section
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        self._draw_section(ax, dims, y, A, P, T, R_h)
        self.canvas.draw()

        self.lbl_status.setText(
            f"<b>{self.spec.name}</b>  \u2014  y = {y:g} m:  "
            f"A = {A:.3f} m\u00b2,  P = {P:.3f} m,  R<sub>h</sub> = {R_h:.3f} m,  T = {T:.3f} m.")

    # ------------------------------------------------------------- drawing
    def _outline_points(self, dims, h_top: float):
        """Sample the true outline of the section from 0 to h_top.
        Returns (right_pts, left_pts) lists of (x, h)."""
        wf = WIDTH_FN[self.spec.name]
        brk = [b for b in BREAK_FN[self.spec.name](dims) if 0.0 < b < h_top]
        hs = []
        for a, b in zip([0.0] + brk, brk + [h_top]):
            n = max(4, int(32 * (b - a) / max(h_top, 1e-9)))
            hs.extend(np.linspace(a, b, n, endpoint=(b == h_top)).tolist())
        right = [(wf(h, dims) / 2.0, h) for h in hs]
        left = [(-x, h) for x, h in reversed(right)]
        return right, left

    def _draw_section(self, ax, dims, y, A, P, T, R_h):
        """Draw the true section outline (from the same width function that
        produces A and P) with the wetted part shaded."""
        name = self.spec.name
        crown_fn = CROWN_FN[name]
        wf = WIDTH_FN[name]
        closed = crown_fn is not None
        h_draw = crown_fn(dims) if closed else y * 1.15
        # For open sections make sure the walls are drawn a bit above water
        if not closed:
            h_draw = max(h_draw, y + 0.02 * max(y, 1.0))
        y_w = min(y, h_draw)

        ax.set_aspect("equal")
        ax.set_xlabel("width  (m)", fontsize=10)
        ax.set_ylabel("height  (m)", fontsize=10)
        ax.set_title(f"{name}  \u2014  y = {y:g} m", fontsize=11)
        ax.grid(alpha=0.3)

        # ---- wetted area shading (true shape, up to the water surface) ----
        right, left = self._outline_points(dims, y_w)
        verts = right + left
        if len(verts) >= 3:
            from matplotlib.patches import Polygon
            ax.add_patch(Polygon(verts, closed=True, facecolor="#1A3A6C",
                                 alpha=0.20, edgecolor="none"))

        # ---- section outline ----
        right, left = self._outline_points(dims, h_draw)
        xs = [p[0] for p in right] + [p[0] for p in left]
        hs = [p[1] for p in right] + [p[1] for p in left]
        if closed:
            xs.append(xs[0]); hs.append(hs[0])
        ax.plot(xs, hs, color="#1A3A6C", lw=2)
        # water surface line
        if y_w > 0 and y_w < h_draw:
            tw = wf(y_w, dims) / 2.0
            ax.plot([-tw, tw], [y_w, y_w], color="#1A3A6C", lw=1, alpha=0.7)

        # ---- limits ----
        w_max = max(wf(h, dims) for h in
                    np.linspace(0.0, h_draw, 128).tolist()) / 2.0
        pad = max(0.3, 0.06 * max(w_max, h_draw))
        ax.set_xlim(-w_max - pad, w_max + pad)
        ax.set_ylim(-pad * 0.5, h_draw + pad)
        # Annotate
        ax.annotate(f"A = {A:.3f} m\u00b2\nP = {P:.3f} m\nR\u2095 = {R_h:.3f} m",
                    xy=(0.02, 0.98), xycoords="axes fraction", ha="left", va="top",
                    fontsize=9, color="#1A3A6C",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#1A3A6C"))

    def on_ok(self):
        if not hasattr(self, "_last"):
            self.lbl_status.setText("<span style='color:#B8500A'>Compute first</span>")
            return
        dims, y, A, P, T, R_h = self._last
        APP_STATE.crossSections = self.spec.name   # store the name of the active section
        APP_STATE.cross_section_result = {
            "type": self.spec.name,
            "dimensions": dims,
            "y_m": y,
            "A_m2": A, "P_m": P, "T_m": T, "R_h_m": R_h,
        }
        self.lbl_status.setText(
            self.lbl_status.text() + "  \u2713 Cross-section committed to APP_STATE.")
        QtWidgets.QApplication.processEvents()
        QtCore.QTimer.singleShot(400, self.close)


# =============================================================================
#  THE FACTORY (called by the MDI shell's open_placeholder)
# =============================================================================
def make_cross_section_dialog(section_type: str) -> CrossSectionDialog:
    """Public factory used by the MDI shell.  Maps the menu-item key
    (which is the original VB6 .frm name) to the corresponding
    SectionSpec, then constructs the dialog.
    """
    keymap = {
        "Rectangular":        "Rectangular",
        "Tropizodal":         "Trapezoidal",
        "Circular":           "Circular",
        "EggShape":           "Egg-shaped",
        "HorseShoe":          "Horseshoe",
        "ModifiedHorseShoe":  "Modified horseshoe",
        "RectangularCorner":  "Rectangular corner",
        "Trangular":          "Triangular",
        "TrangularCorner":    "Triangular corner",
        # Merged-shell menu keys (ui/mdi_main.py Cavitation Analysis
        # cross-section submenu, snake_case)
        "rectangular":         "Rectangular",
        "trangular":           "Triangular",
        "tropizodal":          "Trapezoidal",
        "egg":                 "Egg-shaped",
        "circular":            "Circular",
        "horse_shoe":          "Horseshoe",
        "modified_horse_shoe": "Modified horseshoe",
        "rectangular_corner":  "Rectangular corner",
        "trangular_corner":    "Triangular corner",
    }
    spec_name = keymap.get(section_type, section_type)
    for s in SECTION_SPECS:
        if s.name == spec_name:
            return CrossSectionDialog(s)
    # Fallback: rectangular
    return CrossSectionDialog(SECTION_SPECS[0])
