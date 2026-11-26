"""
test_cross_sections_v132.py - Golden-reference tests for the v1.3.2
cross-section rewrite (cavicuspill/ui/forms/cross_section.py) and the
EM-Py Group E keyed registry (em_py/ui/forms/group_e.py).

Golden sources:
  - Egg-shaped (Baldwin-Latham Form 1): Enfinger (2024) Table 4,
    validated values for D_T = 60 in = 5 ft (egg height D = 7.5 ft):
      d = 0.5 ft : A = 0.699 ft^2, P = 2.318 ft,  B = 2.000 ft
      d = 5.0 ft : A = 18.896 ft^2, P = 11.971 ft, B = 5.000 ft
      d = 7.5 ft : A = 28.713 ft^2, P = 19.825 ft, B = 0.000 ft
  - Standard horseshoe: Merkley (2005) four-circle construction
    (invert circle r=H centered (0,H); side circles r=H centered
    (+-H/2, H/2); crown circle r=H/2 centered (0, H/2)); width = height
    = H; A_full and P_full verified in-repo by independent Simpson
    integration of the exact width function.
  - Simple sections: textbook closed forms (rectangular, trapezoidal,
    circular segment, triangular).
  - Physics invariants: wetted perimeter of any channel at depth y must
    exceed 2y (v1.3.1 shipped a horseshoe with P = 4.667 m at y = 3 m,
    which is impossible; this suite pins the fix).
  - GUI: the merged-shell keyed factories must import GROUP_E_FORMS from
    BOTH cavicuspill and em_py (v1.3.1 shipped em_py without the
    registry, so every EM utility window raised ImportError), and all 9
    cross-section dialogs + 6 EM forms must instantiate offscreen.

Run:  python test_cross_sections_v132.py
"""
import math
import os
import sys
import unittest

# Headless-safe GUI: select the offscreen Qt platform BEFORE any Qt import
# or QApplication (mirrors test_swb.py). Without this, CI runners fall back
# to xcb and abort (no DISPLAY, no libxcb-cursor0 on ubuntu-latest).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cavicuspill.ui.forms.cross_section import (
    GEOM_FN, WIDTH_FN, CROWN_FN, SECTION_SPECS,
    geom_rectangular, geom_trapezoidal, geom_circular, geom_triangular,
    geom_egg_shape, geom_horseshoe, geom_modified_horseshoe,
    geom_rectangular_corner, geom_triangular_corner,
)


def _simpson_width_area(width_fn, dims, h_top, n=20000):
    """Independent numeric area check: A = integral of width dh."""
    if n % 2:
        n += 1
    h = h_top / n
    s = width_fn(0.0, dims) + width_fn(h_top, dims)
    for i in range(1, n):
        s += width_fn(i * h, dims) * (4 if i % 2 else 2)
    return s * h / 3.0


class TestSimpleSectionsClosedForms(unittest.TestCase):
    """Textbook values - guard the already-correct closed forms."""

    def test_rectangular(self):
        A, P, T = geom_rectangular(3.0, {"b (Width)": 5.0})
        self.assertAlmostEqual(A, 15.0, places=9)
        self.assertAlmostEqual(P, 11.0, places=9)
        self.assertAlmostEqual(T, 5.0, places=9)
        self.assertAlmostEqual(A / P, 1.3636363636, places=6)

    def test_trapezoidal(self):
        A, P, T = geom_trapezoidal(3.0, {"b (Width)": 5.0, "Z (Side slope)": 1.0})
        self.assertAlmostEqual(A, 24.0, places=9)
        self.assertAlmostEqual(P, 5.0 + 6.0 * math.sqrt(2.0), places=9)
        self.assertAlmostEqual(T, 11.0, places=9)

    def test_circular(self):
        D = 5.0
        A, P, T = geom_circular(3.0, {"D (Diameter)": D})
        R = D / 2.0
        theta = math.acos((R - 3.0) / R)
        A_ref = R * R * (theta - math.sin(theta) * math.cos(theta))
        P_ref = 2.0 * R * theta
        T_ref = 2.0 * R * math.sin(theta)
        self.assertAlmostEqual(A, A_ref, places=9)
        self.assertAlmostEqual(P, P_ref, places=9)
        self.assertAlmostEqual(T, T_ref, places=9)
        # half full
        A, P, T = geom_circular(2.5, {"D (Diameter)": 5.0})
        self.assertAlmostEqual(A, math.pi * 6.25 / 2.0, places=9)
        self.assertAlmostEqual(P, math.pi * 5.0 / 2.0, places=9)
        self.assertAlmostEqual(T, 5.0, places=9)
        # full pipe
        A, P, T = geom_circular(6.0, {"D (Diameter)": 5.0})
        self.assertAlmostEqual(A, math.pi * 6.25, places=9)
        self.assertAlmostEqual(P, math.pi * 5.0, places=9)
        self.assertAlmostEqual(T, 0.0, places=9)

    def test_triangular(self):
        A, P, T = geom_triangular(3.0, {"Z (Side slope)": 1.0})
        self.assertAlmostEqual(A, 9.0, places=9)
        self.assertAlmostEqual(P, 6.0 * math.sqrt(2.0), places=9)
        self.assertAlmostEqual(T, 6.0, places=9)


class TestEggShapeEnfingerTable4(unittest.TestCase):
    """Baldwin-Latham Form 1 egg vs Enfinger (2024) Table 4 (D_T = 5 ft).

    The Python API takes the egg HEIGHT D (= 1.5 * D_T = 7.5 ft);
    depths 0.5 / 5.0 / 7.5 ft are the maximum depths of Enfinger's
    Regions I / II / III."""

    DIMS = {"D (Height)": 7.5}

    def test_region1_max(self):
        A, P, T = geom_egg_shape(0.5, self.DIMS)
        self.assertAlmostEqual(A, 0.699, places=2)
        self.assertAlmostEqual(P, 2.318, places=2)
        self.assertAlmostEqual(T, 2.000, places=2)

    def test_region2_max(self):
        A, P, T = geom_egg_shape(5.0, self.DIMS)
        self.assertAlmostEqual(A, 18.896, places=2)
        self.assertAlmostEqual(P, 11.971, places=2)
        self.assertAlmostEqual(T, 5.000, places=2)

    def test_region3_full(self):
        A, P, T = geom_egg_shape(7.5, self.DIMS)
        self.assertAlmostEqual(A, 28.713, places=2)
        self.assertAlmostEqual(P, 19.825, places=2)
        self.assertAlmostEqual(T, 0.000, places=6)

    def test_width_matches_numeric_integration(self):
        A, P, T = geom_egg_shape(6.1, self.DIMS)
        A_num = _simpson_width_area(width_ := WIDTH_FN["Egg-shaped"], self.DIMS, 6.1)
        self.assertAlmostEqual(A, A_num, delta=2e-3)

    def test_crown_guard(self):
        with self.assertRaises(ValueError):
            geom_egg_shape(7.6, self.DIMS)


class TestHorseshoeMerkley(unittest.TestCase):
    """USBR standard horseshoe (Merkley 2005) - D = height = max width."""

    DIMS = {"D (Diameter)": 5.0}

    def test_top_width_at_half_height_equals_diameter(self):
        # construction property: T reaches D at half height
        T = WIDTH_FN["Horseshoe"](2.5, self.DIMS)
        self.assertAlmostEqual(T, 5.0, places=9)
        A, P, T2 = geom_horseshoe(2.5, self.DIMS)
        self.assertAlmostEqual(T2, 5.0, places=9)

    def test_full_flow_values(self):
        A, P, T = geom_horseshoe(5.0, self.DIMS)
        A_num = _simpson_width_area(WIDTH_FN["Horseshoe"], self.DIMS, 5.0)
        self.assertAlmostEqual(A / (5.0 ** 2), 0.82932, places=4)
        self.assertAlmostEqual(A, A_num, delta=2e-3)
        # independent closed-form perimeter: invert 2D*acos(1-h1/D) ...
        h1 = (3.0 - math.sqrt(7.0)) / 4.0 * 5.0
        P_ref = (2.0 * 5.0 * math.acos(1.0 - h1 / 5.0)
                 + 2.0 * 5.0 * (math.pi / 2.0 - math.acos((2.5 - h1) / 5.0))
                 + math.pi * 2.5)
        self.assertAlmostEqual(P, P_ref, places=9)

    def test_regression_v131_impossible_perimeter(self):
        """v1.3.1 gave P = 4.667 m for D=5, y=3 (less than 2y = 6 m).
        The exact construction gives P ~= 9.49 m."""
        A, P, T = geom_horseshoe(3.0, self.DIMS)
        self.assertGreater(P, 6.0)
        self.assertAlmostEqual(P, 9.485, places=2)
        self.assertAlmostEqual(A, 13.399, places=2)

    def test_width_continuity_at_transitions(self):
        h1 = (3.0 - math.sqrt(7.0)) / 4.0 * 5.0
        wf = WIDTH_FN["Horseshoe"]
        for h in (h1, 2.5):
            lo = wf(h - 1e-9, self.DIMS)
            hi = wf(h + 1e-9, self.DIMS)
            self.assertAlmostEqual(lo, hi, places=6)

    def test_crown_guard(self):
        with self.assertRaises(ValueError):
            geom_horseshoe(5.1, self.DIMS)


class TestModifiedHorseshoe(unittest.TestCase):
    DIMS = {"b (Width)": 5.0}

    def test_full_flow_closed_form(self):
        b = 5.0
        A, P, T = geom_modified_horseshoe(b, self.DIMS)
        self.assertAlmostEqual(A, b * b / 2.0 + math.pi * b * b / 8.0, places=9)
        self.assertAlmostEqual(P, 2.0 * b + math.pi * b / 2.0, places=9)
        self.assertAlmostEqual(T, 0.0, places=9)

    def test_rectangular_part(self):
        A, P, T = geom_modified_horseshoe(2.5, self.DIMS)
        self.assertAlmostEqual(A, 5.0 * 2.5, places=9)
        self.assertAlmostEqual(P, 5.0 + 5.0, places=9)
        self.assertAlmostEqual(T, 5.0, places=9)

    def test_matches_numeric_integration(self):
        A, P, T = geom_modified_horseshoe(4.2, self.DIMS)
        A_num = _simpson_width_area(WIDTH_FN["Modified horseshoe"], self.DIMS, 4.2)
        self.assertAlmostEqual(A, A_num, delta=2e-3)

    def test_crown_guard(self):
        with self.assertRaises(ValueError):
            geom_modified_horseshoe(5.01, self.DIMS)


class TestRectangularCorner(unittest.TestCase):
    DIMS = {"b (Width)": 5.0, "r (Radius)": 0.5}

    def test_above_rounding_closed_form(self):
        A, P, T = geom_rectangular_corner(3.0, self.DIMS)
        self.assertAlmostEqual(A, 5.0 * 3.0 - 2 * 0.25 + math.pi * 0.125, places=9)
        self.assertAlmostEqual(P, 6.0 + 5.0 - 2.0 + math.pi * 0.5, places=9)
        self.assertAlmostEqual(T, 5.0, places=9)

    def test_within_rounding_matches_numeric(self):
        A, P, T = geom_rectangular_corner(0.3, self.DIMS)
        A_num = _simpson_width_area(WIDTH_FN["Rectangular corner"], self.DIMS, 0.3)
        self.assertAlmostEqual(A, A_num, delta=1e-3)
        self.assertGreater(P, 5.0 - 1.0)  # bottom strip wetted

    def test_zero_radius_limit_is_plain_rectangular(self):
        dims0 = {"b (Width)": 5.0, "r (Radius)": 1e-9}
        A1, P1, T1 = geom_rectangular_corner(3.0, dims0)
        A2, P2, T2 = geom_rectangular(3.0, {"b (Width)": 5.0})
        self.assertAlmostEqual(A1, A2, places=6)
        self.assertAlmostEqual(P1, P2, places=6)


class TestTriangularCorner(unittest.TestCase):
    DIMS = {"Z (Side slope)": 1.0, "r (Radius)": 0.5}

    def test_zero_radius_limit_is_plain_triangular(self):
        dims0 = {"Z (Side slope)": 1.0, "r (Radius)": 1e-9}
        A1, P1, T1 = geom_triangular_corner(3.0, dims0)
        A2, P2, T2 = geom_triangular(3.0, {"Z (Side slope)": 1.0})
        self.assertAlmostEqual(A1, A2, places=6)
        self.assertAlmostEqual(P1, P2, places=6)
        self.assertAlmostEqual(T1, T2, places=6)

    def test_matches_numeric_integration(self):
        A, P, T = geom_triangular_corner(3.0, self.DIMS)
        # depth measured from the invert (circle bottom): offset h0
        Z, r = 1.0, 0.5
        h0 = r * math.sqrt(2.0) - r
        A_num = _simpson_width_area(
            lambda h, d: WIDTH_FN["Triangular corner"](h + h0, d), self.DIMS, 3.0)
        self.assertAlmostEqual(A, A_num, delta=2e-3)

    def test_perimeter_exceeds_two_y(self):
        A, P, T = geom_triangular_corner(3.0, self.DIMS)
        self.assertGreater(P, 6.0)


class TestPhysicsInvariants(unittest.TestCase):
    """P > 2y for every section at a range of depths; A monotone in y."""

    def _cases(self):
        cases = [
            ("Rectangular", {"b (Width)": 5.0}, None),
            ("Trapezoidal", {"b (Width)": 5.0, "Z (Side slope)": 1.0}, None),
            ("Circular", {"D (Diameter)": 5.0}, 5.0),
            ("Egg-shaped", {"D (Height)": 3.0}, 3.0),
            ("Horseshoe", {"D (Diameter)": 5.0}, 5.0),
            ("Modified horseshoe", {"b (Width)": 5.0}, 5.0),
            ("Rectangular corner", {"b (Width)": 5.0, "r (Radius)": 0.5}, None),
            ("Triangular", {"Z (Side slope)": 1.0}, None),
            ("Triangular corner", {"Z (Side slope)": 1.0, "r (Radius)": 0.5}, None),
        ]
        for name, dims, crown in cases:
            for frac in (0.15, 0.4, 0.7):
                y = crown * frac if crown else 3.0
                yield name, dims, y

    def test_perimeter_exceeds_two_y(self):
        for name, dims, y in self._cases():
            A, P, T = GEOM_FN[name](y=y, dims=dims)
            self.assertGreater(P, 2.0 * y, msg=f"{name}: P={P} <= 2y={2*y}")
            self.assertGreater(A, 0.0, msg=name)

    def test_area_monotone(self):
        for name, dims, y in self._cases():
            geom = GEOM_FN[name]
            A1, _, _ = geom(y=0.7 * y, dims=dims)
            A2, _, _ = geom(y=y, dims=dims)
            self.assertLess(A1, A2, msg=name)

    def test_spec_defaults_are_within_crown(self):
        """The dialog defaults must open inside the valid depth range."""
        for spec in SECTION_SPECS:
            dims = {label: default for label, _, default in spec.inputs}
            y = 3.0
            if spec.name == "Egg-shaped":
                y = 1.5
            elif spec.name in ("Horseshoe", "Modified horseshoe"):
                y = 2.5
            crown_fn = CROWN_FN[spec.name]
            if crown_fn is not None:
                self.assertLessEqual(y, crown_fn(dims), msg=spec.name)
            A, P, T = GEOM_FN[spec.name](y=y, dims=dims)  # must not raise
            self.assertGreater(A, 0.0)


class TestGroupERegistries(unittest.TestCase):
    """v1.3.1 regression: em_py shipped without GROUP_E_FORMS, so every
    EM utility window in the merged shell raised ImportError."""

    def test_cavicuspill_registry(self):
        from cavicuspill.ui.forms.group_e import GROUP_E_FORMS as REG
        self.assertEqual(set(REG.keys()), {"e1", "e2", "e3", "e4", "e5", "e6"})

    def test_em_py_registry(self):
        from em_py.ui.forms.group_e import GROUP_E_FORMS as REG
        self.assertEqual(set(REG.keys()), {"e1", "e2", "e3", "e4", "e5", "e6"})

    def test_em_titles_match_merged_shell_menu(self):
        from em_py.ui.forms.group_e import GROUP_E_FORMS as REG
        expected = {
            "e1": "EM1. Station Grid",
            "e2": "EM2. Hydrograph Viewer",
            "e3": "EM3. Boundary Layer Profile",
            "e4": "EM4. Data Compare",
            "e5": "EM5. Exporter",
            "e6": "EM6. Report Generator",
        }
        for key, title in expected.items():
            self.assertEqual(REG[key][0], title, msg=key)


class TestGuiSmokeOffscreen(unittest.TestCase):
    """All dialogs/forms instantiate offscreen (self-guards QT_QPA)."""

    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_all_cross_section_dialogs_open(self):
        from cavicuspill.ui.forms.cross_section import CrossSectionDialog
        for spec in SECTION_SPECS:
            dlg = CrossSectionDialog(spec)
            self.assertIsNotNone(dlg._last, msg=spec.name)   # initial compute OK
            status = dlg.lbl_status.text()
            self.assertNotIn("error", status.lower(), msg=f"{spec.name}: {status}")
            self.assertTrue(hasattr(dlg, "canvas"))
            dlg.close()

    def test_cross_section_factory_keys(self):
        from cavicuspill.ui.forms.cross_section import make_cross_section_dialog
        for key in ("rectangular", "tropizodal", "circular", "egg", "horse_shoe",
                    "modified_horse_shoe", "rectangular_corner", "trangular",
                    "trangular_corner"):
            dlg = make_cross_section_dialog(key)
            self.assertIsNotNone(dlg._last, msg=key)
            dlg.close()

    def test_em_forms_accept_parent_and_open(self):
        from em_py.ui.forms.group_e import GROUP_E_FORMS as REG
        from cavicuspill.ui.forms.group_e import GROUP_E_FORMS as CAV_REG
        for key, (_title, cls) in REG.items():
            form = cls(None)                      # parent=None (standalone)
            self.assertTrue(form.windowTitle().startswith("EM"), msg=key)
            form.close()
        for key, (_title, cls) in CAV_REG.items():
            form = cls(None)                      # QMdiSubWindow parent
            form.close()

    def test_crown_exceeded_shows_status_error_not_crash(self):
        from cavicuspill.ui.forms.cross_section import CrossSectionDialog, SECTION_SPECS
        spec = next(s for s in SECTION_SPECS if s.name == "Horseshoe")
        dlg = CrossSectionDialog(spec)
        dlg.txt["y (Flow depth)"].setText("6.0")   # crown at 5.0
        dlg._compute_and_draw()
        self.assertIn("exceeds", dlg.lbl_status.text())
        self.assertFalse(hasattr(dlg, "_last") and dlg._last and
                         dlg._last[1] == 6.0)      # not committed
        dlg.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
