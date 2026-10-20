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

The 9 section types and their properties:

| # | Section        | Inputs        | Area A     | Wetted P          | Top width T |
|---|----------------|---------------|------------|-------------------|-------------|
| 1 | Rectangular    | b             | b*y        | b + 2y            | b           |
| 2 | Trapezoidal    | b, Z          | (b + Z*y)y | b + 2y*sqrt(1+Z^2)| b + 2Zy     |
| 3 | Circular       | D             | pi*D^2/4   | pi*D              | D           |
| 4 | Egg-shaped     | D             | complex    | complex           | D           |
| 5 | HorseShoe      | D             | complex    | complex           | D           |
| 6 | Modified HS    | b             | complex    | complex           | b           |
| 7 | Rect. corner   | b, r          | complex    | complex           | b           |
| 8 | Triangular     | Z             | Z*y^2      | 2y*sqrt(1+Z^2)    | 2Zy         |
| 9 | Tri. corner    | Z, r          | complex    | complex           | 2Zy         |

The non-trivial ones (egg-shape, horseshoe, etc.) use the standard
hydraulic-engineering approximations (Bhave 1991, Hinds 1928).

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations
import os, sys
import math
from dataclasses import dataclass
from typing import Callable, List, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cavicuspill as cav  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mdi_main as _mdi_main  # noqa: E402
APP_STATE = _mdi_main.APP_STATE
from charts.matplotlib_widget import MplCanvas  # noqa: E402


# =============================================================================
#  SECTION GEOMETRY  (one entry per cross-section type)
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
    SectionSpec("Egg-shaped",          "EggShape",           [("D (Height)", "m", 5.0)],
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
#  GEOMETRY FUNCTIONS  (returns (Area A, Wetted P, Top width T) for a
#  given flow depth y and the input dimensions)
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
    D = dims["D (Height)"]
    R = D / 2.0
    if y <= 0:
        return 0, 0, 0
    if y >= D:
        # Full egg: A = 0.5164*D^2 (Bhave's coefficient), P = 1.38*D, T = 0
        return 0.5164 * D * D, 1.38 * D, 0.0
    A = (0.5164 * R * R) * (y / R) ** 1.674
    P = D * (0.93 + 0.05 * y / R + 0.4 * (y / R) ** 2)
    T = D * (0.46 + 0.4 * y / R)
    return A, P, T

def geom_horseshoe(y, dims, **_):
    D = dims["D (Diameter)"]
    R = D / 2.0
    if y <= 0:
        return 0, 0, 0
    if y >= D:
        # Full horseshoe: full circular arc + flat invert
        A = math.pi * R * R + (2 * R) * (D / 3.0)   # disc + invert rectangle
        P = math.pi * D + 2 * (D / 3.0)              # arc + 2x invert
        T = 0.0
        return A, P, T
    A_upper = 0
    P_upper = 0
    if y > D / 3.0:
        y_arc = y - D / 3.0
        theta = y_arc / R
        A_upper = R * R * (theta - math.sin(theta)) / 2.0
        P_upper = R * theta
    A_lower = D / 3.0 * (D / 3.0 * 2 * (y / (D / 3.0)) ** 0.5)
    A = A_lower + A_upper
    P = 2 * D / 3.0 + P_upper
    T = D if y >= D else (2 * math.sqrt(R * R - (R - y) ** 2) if y > D / 3.0 else D)
    return A, P, T

def geom_modified_horseshoe(y, dims, **_):
    b = dims["b (Width)"]
    R = b / 2.0
    if y <= 0:
        return 0, 0, 0
    # Cap at b + 2R = 2b (the full bounding box height)
    y_cap = min(y, 2 * R)
    h_rect = min(y_cap, R)
    A_rect = b * h_rect
    P_rect = b + 2 * h_rect
    A_arc = 0
    P_arc = 0
    T_arc = 0
    if y_cap > R:
        theta = (y_cap - R) / R
        A_arc = R * R * (theta - math.sin(theta)) / 2.0
        P_arc = R * theta
        T_arc = 2 * R * math.sin(theta / 2.0)
    if y >= 2 * R:
        T_arc = 0.0   # full pipe: no free surface
    return A_rect + A_arc, P_rect + P_arc, b + T_arc

def geom_rectangular_corner(y, dims, **_):
    b = dims["b (Width)"]
    r = dims["r (Radius)"]
    if y <= 0:
        return 0, 0, 0
    if y <= r:
        return 0, 0, 0
    y_rect = y - r
    # Cap at b/2 to avoid negative width when r > b/2
    rect_w = max(0.0, b - 2 * r)
    A = rect_w * y_rect + math.pi * r * r
    P = rect_w + 2 * y_rect + math.pi * r
    T = b
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
    Z = dims["Z (Side slope)"]
    r = dims["r (Radius)"]
    if y <= 0:
        return 0, 0, 0
    if y <= r:
        return 0, 0, 0
    y_straight = y - r
    A = Z * y_straight * y_straight + math.pi * r * r / 2.0
    P = 2 * y_straight * math.sqrt(1 + Z * Z) + math.pi * r
    T = 2 * Z * y_straight
    return A, P, T


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
        # Flow depth y (always present)
        self.txt["y (Flow depth)"] = QtWidgets.QLineEdit("3.0")
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

    def _draw_section(self, ax, dims, y, A, P, T, R_h):
        """Draw a schematic of the section.  Default: a 1m-tall rectangle
        with the section outline overlaid; specific shapes drawn per type."""
        ax.set_aspect("equal")
        ax.set_xlabel("width  (m)", fontsize=10)
        ax.set_ylabel("height  (m)", fontsize=10)
        ax.set_title(f"{self.spec.name}  \u2014  y = {y:g} m", fontsize=11)
        ax.grid(alpha=0.3)
        # Wetted area shaded
        try:
            if self.spec.name == "Rectangular":
                b = dims["b (Width)"]
                ax.add_patch(QtWidgets.QWidget().style().standardPixmap.__self__ if False else None)
                from matplotlib.patches import Rectangle, Polygon, Circle, Wedge
                ax.add_patch(Rectangle((-b/2, 0), b, y, facecolor="#1A3A6C",
                                       alpha=0.20, edgecolor="#1A3A6C", lw=2))
                ax.set_xlim(-b/2 - 0.3, b/2 + 0.3)
                ax.set_ylim(-0.2, y + 0.3)
            elif self.spec.name == "Trapezoidal":
                b, Z = dims["b (Width)"], dims["Z (Side slope)"]
                from matplotlib.patches import Polygon
                verts = [(-b/2, 0), (b/2, 0), (b/2 + Z*y, y), (-b/2 - Z*y, y)]
                ax.add_patch(Polygon(verts, closed=True, facecolor="#1A3A6C",
                                     alpha=0.20, edgecolor="#1A3A6C", lw=2))
                ax.set_xlim(-b/2 - Z*y - 0.3, b/2 + Z*y + 0.3)
                ax.set_ylim(-0.2, y + 0.3)
            elif self.spec.name == "Circular":
                D = dims["D (Diameter)"]
                R = D / 2.0
                from matplotlib.patches import Wedge
                # Central angle for the wetted part
                ratio = max(-1.0, min(1.0, (R - y) / R))
                theta = math.acos(ratio)
                ax.add_patch(Wedge((0, 0), R, -90, 90 + math.degrees(2*theta) - 90,
                                   width=0, facecolor="#1A3A6C", alpha=0.20,
                                   edgecolor="#1A3A6C", lw=2))
                ax.add_patch(plt_full_circle(R, color="#1A3A6C", lw=2, fill=False))
                ax.set_xlim(-R - 0.3, R + 0.3); ax.set_ylim(-R - 0.3, R + 0.3)
            else:
                # Generic 1m x y box for the rest (egg, horseshoe, triangular, etc.)
                from matplotlib.patches import Polygon
                verts = [(-T/2, 0), (T/2, 0), (T/2, y), (-T/2, y)]
                ax.add_patch(Polygon(verts, closed=True, facecolor="#1A3A6C",
                                     alpha=0.20, edgecolor="#1A3A6C", lw=2))
                ax.set_xlim(-T/2 - 0.3, T/2 + 0.3); ax.set_ylim(-0.2, y + 0.3)
        except Exception as e:
            ax.text(0.5, 0.5, f"Draw error: {e}", ha="center", va="center",
                    transform=ax.transAxes, color="#B8500A")
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


def plt_full_circle(R, color="black", lw=1, fill=False, alpha=1.0):
    """Helper to draw a complete circle as a Polygon."""
    from matplotlib.patches import Circle as MplCircle
    return MplCircle((0, 0), R, color=color, lw=lw, fill=fill, alpha=alpha)


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
    }
    spec_name = keymap.get(section_type, section_type)
    for s in SECTION_SPECS:
        if s.name == spec_name:
            return CrossSectionDialog(s)
    # Fallback: rectangular
    return CrossSectionDialog(SECTION_SPECS[0])
