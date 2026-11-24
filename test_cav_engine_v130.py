"""
test_cav_engine_v130.py - Golden-reference tests for the Cavicuspill
calculation engine added in v1.3.0 (cavicuspill/__init__.py).

Golden sources:
  - Flood routing: the published benchmark "Example 1" (thesis Tables 4-4
    to 4-9; Zenodo benchmark_data/Flood_Routing_Results.csv; peak outflow
    1475.42 m3/s at t = 16 h for L = 70 m, per Example1_Output.txt).
    NOTE: in the Zenodo CSV the Outflow_L80 column tail (t >= 32 h) is a
    copy artifact of the L75 column; the authoritative L80 tail comes from
    thesis Table 4-9 (110.66, 76.41, 53.1, 37.3, 26.62), which the engine
    reproduces.
  - G-Q curve: thesis Table 4-4 (L = 70, first rows, dt = 1 h printing
    convention; routing itself uses dt = 2 h).
  - Isolated-roughness index: EM-42 (Falvey 1990) fig. 2-5 coefficients
    and the worked example sigma_r = 0.565 quoted in the manuscript.
  - WES design: closed-form inversion of Q = c L H_e^1.5 (manuscript
    Eq. 4) and the Design of Small Dams K/P table.
  - Standard step: independent RK4 integration of the GVF ODE
    dy/dx = (S0 - Sf) / (1 - Fr^2) (manuscript Eq. 5).

Run:  python test_cav_engine_v130.py
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import cavicuspill as cav

# --------------------------------------------------------------------------
# Golden vectors (thesis Example 1)
# --------------------------------------------------------------------------
CREST = 55.0
RES_H = np.array([55.0, 56.0, 57.0, 58.0, 59.0, 60.0])
RES_V = np.array([42.0e6, 45.0e6, 50.0e6, 53.0e6, 57.0e6, 62.0e6])
N2 = 10
DELTA_T = 2.0            # hours (exe benchmark convention)

T_H = np.arange(0.0, 41.0, 2.0)
INFLOW_Q = np.array([0, 10, 26, 52, 176, 690, 1483, 1828, 1638, 966, 552,
                     310, 172, 103, 60, 52, 34, 20, 7, 5, 0], dtype=float)

GOLDEN_L70 = [0.00, 0.56, 2.50, 7.81, 33.36, 176.40, 523.81, 1187.30,
              1475.42, 1385.06, 1041.01, 687.55, 427.16, 320.77, 239.64,
              182.04, 134.32, 91.22, 63.22, 44.46, 32.02]
GOLDEN_L75 = [0.00, 0.60, 2.67, 8.27, 35.19, 186.26, 541.97, 1227.49,
              1513.06, 1398.82, 1021.42, 653.87, 424.13, 315.21, 233.39,
              176.09, 120.94, 82.96, 57.44, 40.40, 28.97]
# CSV rows t <= 30 h + thesis Table 4-9 tail for t >= 32 h (see module doc)
GOLDEN_L80 = [0.00, 0.63, 2.83, 8.72, 36.95, 195.84, 558.89, 1264.99,
              1547.38, 1407.48, 1002.75, 622.86, 421.97, 310.40, 227.76,
              167.00, 110.66, 76.41, 53.10, 37.30, 26.62]


def _example1_setup():
    raw = cav.ReservoirTable(e=CREST, h=RES_H, V=RES_V)
    fine = cav.interpolate_reservoir_table(raw.h, raw.V, N2)
    res = cav.ReservoirTable(e=CREST, h=fine[:, 0], V=fine[:, 1])
    cfg = cav.SpillwayConfig(L_min=70.0, L_max=80.0, b=5.0, c=2.225,
                             deltaT=DELTA_T)
    curves = cav.precompute_gq_curves(res, cfg)
    inflow = cav.InflowHydrograph(n=len(T_H), t_h=T_H, Q=INFLOW_Q)
    return res, cfg, curves, inflow


class TestFineGrid(unittest.TestCase):
    def test_51_points_and_first_values(self):
        fine = cav.interpolate_reservoir_table(RES_H, RES_V, N2)
        self.assertEqual(fine.shape, (51, 2))
        self.assertAlmostEqual(fine[1, 0], 55.1, places=9)
        self.assertAlmostEqual(fine[1, 1], 42.3e6, delta=1.0)   # thesis 3-4
        self.assertAlmostEqual(fine[-1, 0], 60.0, places=9)


class TestGQCurves(unittest.TestCase):
    def test_thesis_table_4_4_dt1(self):
        # Thesis printed its G table with dt = 1 h; formulas must match.
        res, _, _, _ = _example1_setup()
        cfg1 = cav.SpillwayConfig(L_min=70.0, L_max=80.0, b=5.0, c=2.225,
                                  deltaT=1.0)
        L, Q, G = cav.precompute_gq_curves(res, cfg1)[0]
        self.assertAlmostEqual(L, 70.0, places=9)
        self.assertAlmostEqual(G[0], 23333.33, delta=0.01)
        self.assertAlmostEqual(G[1], 23504.93, delta=0.01)
        self.assertAlmostEqual(G[2], 23680.60, delta=0.01)
        self.assertAlmostEqual(Q[1], 4.93, delta=0.01)
        self.assertAlmostEqual(Q[2], 13.93, delta=0.01)

    def test_g0_dt2(self):
        res, _, _, _ = _example1_setup()
        _, cfg, curves, _ = _example1_setup()
        L, Q, G = curves[0]
        self.assertAlmostEqual(G[0], 11666.67, delta=0.01)
        self.assertAlmostEqual(Q[1], 4.93, delta=0.01)
        self.assertEqual(len(curves), 3)          # 70, 75, 80


class TestPulseRouting(unittest.TestCase):
    def test_benchmark_columns(self):
        _, _, curves, inflow = _example1_setup()
        for (L, Qg, Gg), golden in zip(
                curves, (GOLDEN_L70, GOLDEN_L75, GOLDEN_L80)):
            JX, MO = cav.pulse_method_routing(inflow, (L, Qg, Gg))
            self.assertEqual(len(MO), len(T_H))
            for i, (got, want) in enumerate(zip(MO, golden)):
                self.assertAlmostEqual(got, want, delta=0.02,
                                       msg=f"L={L:g}, t={T_H[i]:g} h")

    def test_peak(self):
        _, _, curves, inflow = _example1_setup()
        JX, MO = cav.pulse_method_routing(inflow, curves[0])
        i_pk = int(np.argmax(MO))
        self.assertAlmostEqual(MO[i_pk], 1475.42, delta=0.01)
        self.assertEqual(T_H[i_pk], 16.0)


class TestWesDesign(unittest.TestCase):
    def test_closed_form(self):
        Q_d, L, c = 2000.0, 75.0, 2.225
        d = cav.wes_design(Q_d=Q_d, L=L, c=c, upstream_slope="3V:0H")
        H_e = (Q_d / (c * L)) ** (2.0 / 3.0)
        V1 = Q_d / (L * H_e)
        self.assertAlmostEqual(d["H_e"], H_e, places=12)
        self.assertAlmostEqual(d["V_1"], V1, places=12)
        self.assertAlmostEqual(d["H_d"], H_e - V1 ** 2 / (2 * cav.GRAVITY),
                               places=12)
        self.assertAlmostEqual(c * L * d["H_e"] ** 1.5, Q_d, places=9)

    def test_kp_table_consistency(self):
        for slope, (K, P) in cav.WES_KP_TABLE.items():
            co = cav.WES_COEFFS[slope]
            self.assertAlmostEqual(co["K"], K, places=12)
            self.assertAlmostEqual(co["P"], P, places=12)


class TestCavitationIndex(unittest.TestCase):
    def test_em42_anchor_triangles(self):
        # Manuscript verification section: H = 2 mm at x = 10.0005 m,
        # V = 16.079 m/s, nu(10C) = 1.307e-6, delta = 0.1148 m -> 0.565
        sig = cav.cavitation_index_singular_roughness(
            V_b=16.079, H=0.002, delta=0.1148, T=10.0)
        self.assertAlmostEqual(sig, 0.565, delta=0.001)

    def test_six_classes_finite(self):
        for cls in cav.ROUGHNESS_CLASSES:
            s = cav.cavitation_index_singular_roughness(
                16.079, 0.002, 0.1148, 10.0, cls)
            self.assertTrue(math.isfinite(s) and s > 0)

    def test_flow_index_hand_value(self):
        rho, pv, _ = cav.water_properties(20.0)
        self.assertAlmostEqual(rho, 998.228, places=6)
        self.assertAlmostEqual(pv, 2330.0, places=6)
        sig = cav.cavitation_index_flow(150000.0, 30.0, 20.0)
        self.assertAlmostEqual(sig, (150000.0 - 2330.0)
                               / (0.5 * 998.228 * 900.0), places=12)

    def test_uniform_identity_4f(self):
        f = 8 * cav.GRAVITY * 2.0 * 0.01 / 400.0
        self.assertAlmostEqual(cav.cavitation_index_uniform(20.0, 2.0, 0.01),
                               4 * f, places=12)


class TestStandardStep(unittest.TestCase):
    def test_matches_rk4_gvf_integration(self):
        Q, b, nm, S0, y0, dx, nst = 1500.0, 50.0, 0.014, 0.10, 1.0, 1.0, 47
        x, y, V = cav.standard_step(Q, b, nm, S0, y0, dx, nst)
        self.assertEqual(len(x), nst + 1)

        def fric(yy):
            v = Q / (b * yy)
            R = b * yy / (b + 2 * yy)
            return nm ** 2 * v * v / R ** (4.0 / 3.0)

        def froude(yy):
            v = Q / (b * yy)
            return v / math.sqrt(cav.GRAVITY * yy)

        def rhs(yy):
            return (S0 - fric(yy)) / (1.0 - froude(yy) ** 2)

        y_rk, h = y0, dx / 1000.0
        y_ref = [y0]
        for _ in range(nst):
            for _ in range(1000):
                k1 = rhs(y_rk)
                k2 = rhs(y_rk + 0.5 * h * k1)
                k3 = rhs(y_rk + 0.5 * h * k2)
                k4 = rhs(y_rk + h * k3)
                y_rk += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
            y_ref.append(y_rk)
        self.assertLess(float(np.max(np.abs(np.array(y_ref) - y))), 2e-3)

    def test_energy_balance_residual(self):
        Q, b, nm, S0, y0, dx, nst = 1500.0, 50.0, 0.014, 0.10, 1.0, 1.0, 47
        x, y, V = cav.standard_step(Q, b, nm, S0, y0, dx, nst)

        def E(yy):
            return yy + (Q / (b * yy)) ** 2 / (2 * cav.GRAVITY)

        def Sff(yy):
            v = Q / (b * yy)
            R = b * yy / (b + 2 * yy)
            return nm ** 2 * v * v / R ** (4.0 / 3.0)

        worst = max(abs(E(y[i]) + (x[-1] - x[i]) * S0
                        - (E(y[i + 1]) + (x[-1] - x[i + 1]) * S0)
                        - 0.5 * (Sff(y[i]) + Sff(y[i + 1])) * dx)
                    for i in range(nst))
        self.assertLess(worst, 1e-5)

    def test_subcritical_branch(self):
        x, y, V = cav.standard_step(10.0, 5.0, 0.02, 0.0005, 2.5, 1.0, 100)
        self.assertTrue(bool((y > 0).all()))
        self.assertTrue(bool((V > 0).all()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
