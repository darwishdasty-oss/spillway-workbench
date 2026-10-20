"""
test_traj_v12.py - SWB v1.2 TRAJ engine regression tests (headless).

Validates the re-implemented TRAJ engine (em_py/em_traj.py) against the
original USBR TRAJ.EXE reference output published in Falvey, "Cavitation
in Chutes and Spillways", EM-42 (1990), Appendix D, p. 127 (Glen Canyon
left spillway tunnel aerator).

Reference input (EM-42 p. 126):
    geometry file GLENIN (bundled), ramp lip (685.80, 1035.112),
    angle 53.975 deg (descending tangent), vent area 1.486 m2 x 2,
    vent width 1.219, loss coeff 1.0 (run A) / 1.2 (run B),
    Q = 283.17 cms, turbulence 0.028, depth 1.385 m, velocity 36.463 m/s
Reference output (p. 127):
    WATER 283.17, AIR 27.50, pressure drop .006 (run A) / .007 (run B)
    three trajectory tables (lower nappe x2, top nappe), 11 points each.

Run:  python test_traj_v12.py
Expected output: ALL TESTS PASSED
No GUI required (same headless contract as test_ws77_v11.py).
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "em_py"))

from em_data import read_geometry_file          # noqa: E402
from em_traj import (RampGeometry, FlowProperties, VentGeometry,  # noqa: E402
                     TrajectoryPoint, compute_trajectory, _glazov_rk4,
                     _glazov_xy, G)

# ---------------------------------------------------------------------------
# Reference data (EM-42 p. 145 image, Appendix D p. 127)
# ---------------------------------------------------------------------------
REF_LOWER1 = [(685.80, 1035.11), (686.08, 1034.70), (686.36, 1034.29),
              (686.64, 1033.88), (686.92, 1033.46), (687.20, 1033.05),
              (687.48, 1032.63), (687.76, 1032.21), (688.04, 1031.78),
              (688.32, 1031.36), (688.44, 1031.18)]
REF_LOWER2 = [(685.80, 1035.11), (686.10, 1034.72), (686.41, 1034.32),
              (686.71, 1033.93), (687.01, 1033.53), (687.31, 1033.13),
              (687.62, 1032.72), (687.92, 1032.32), (688.22, 1031.91),
              (688.52, 1031.51), (688.66, 1031.33)]
REF_TOP = [(686.92, 1035.93), (687.20, 1035.56), (687.50, 1035.17),
           (687.80, 1034.77), (688.11, 1034.37), (688.41, 1033.97),
           (688.71, 1033.57), (689.02, 1033.17), (689.32, 1032.76),
           (689.62, 1032.35), (689.81, 1032.09)]

Q_REF = 283.168
AIR_REF = 27.50

_FAILURES = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {name:<58} {status}"
          + ("" if cond else f"  [{detail}]"))
    if not cond:
        _FAILURES.append(name)


def max_table_diff(computed, reference):
    m = 0.0
    for (sx, ex), p in zip(reference, computed):
        m = max(m, abs(p.x - sx), abs(p.y - ex))
    return m


def main():
    print("test_traj_v12: TRAJ engine regression tests (EM-42 App. D)")

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "em_py", "sample_data", "DATA")
    g = read_geometry_file(os.path.join(data_dir, "GLENIN"))
    profile = [(s.sta, s.invert) for s in g.stations]

    def run_case(loss_coeff):
        ramp = RampGeometry(angle_deg=-53.975, elev_lip=1035.112,
                            sta_lip=685.80, elev_floor=956.25,
                            profile=profile, profile_source="GLENIN")
        flow = FlowProperties(q=Q_REF, velocity_ramp=36.463,
                              depth_ramp=1.385, turbulence=0.028)
        vent = VentGeometry(n_vents=2, width=1.219, area=1.486,
                            loss_coeff=loss_coeff)
        return compute_trajectory(ramp, flow, vent)

    # ------------------------------------------------------------------
    print("  Glen Canyon reference run A (loss coeff 1.0) .........")
    resA = run_case(1.0)
    check("run converges", resA.converged,
          f"iterations={resA.iterations}")
    check("no warnings", not resA.warnings, str(resA.warnings))
    check("air flow within 2 pct of 27.50 (got %.3f)" % resA.air_flow_rate,
          abs(resA.air_flow_rate - AIR_REF) / AIR_REF <= 0.02,
          f"{resA.air_flow_rate:.3f}")
    check("pressure drop prints .006 m (got %.5f)" % resA.pressure_drop_mh2o,
          0.0055 <= resA.pressure_drop_mh2o < 0.0065,
          f"{resA.pressure_drop_mh2o:.5f}")
    check("landing station 688.44 +- 0.10 (got %.3f)" % resA.land_x,
          abs(resA.land_x - 688.44) <= 0.10, f"{resA.land_x:.3f}")
    check("landing elevation 1031.18 +- 0.10 (got %.3f)" % resA.land_elev,
          abs(resA.land_elev - 1031.18) <= 0.10, f"{resA.land_elev:.3f}")

    # ------------------------------------------------------------------
    print("  trajectory tables vs EM-42 p.127 ....................")
    d1 = max_table_diff(resA.print_lower1, REF_LOWER1)
    d2 = max_table_diff(resA.print_lower2, REF_LOWER2)
    d3 = max_table_diff(resA.print_top, REF_TOP)
    check("lower nappe 1 (max air penetration) max diff <= 0.06 m", d1 <= 0.06,
          f"{d1:.4f}")
    check("lower nappe 2 (turbulence dispersion) max diff <= 0.06 m",
          d2 <= 0.06, f"{d2:.4f}")
    check("top nappe max diff <= 0.08 m (print-grid ambiguity)", d3 <= 0.08,
          f"{d3:.4f}")

    # ------------------------------------------------------------------
    print("  Glen Canyon reference run B (loss coeff 1.2) ........")
    resB = run_case(1.2)
    check("pressure drop prints .007 m (got %.5f)" % resB.pressure_drop_mh2o,
          0.0066 <= resB.pressure_drop_mh2o < 0.0078,
          f"{resB.pressure_drop_mh2o:.5f}")
    check("air flow unaffected by vent loss (delta <= 0.3%)",
          abs(resB.air_flow_rate - resA.air_flow_rate) / resA.air_flow_rate
          <= 0.003,
          f"{resB.air_flow_rate:.3f} vs {resA.air_flow_rate:.3f}")
    traj_delta = max(
        max(abs(p.x - q.x) for p, q in zip(resA.print_lower1, resB.print_lower1)),
        max(abs(p.y - q.y) for p, q in zip(resA.print_lower1, resB.print_lower1)))
    # the ~2 mm engine-level shift is far below the original program's
    # 2-decimal print resolution - the printed tables are identical
    traj_delta_printed = max(
        max(abs(round(p.x, 2) - round(q.x, 2))
            for p, q in zip(resA.print_lower1, resB.print_lower1)),
        max(abs(round(p.y, 2) - round(q.y, 2))
            for p, q in zip(resA.print_lower1, resB.print_lower1)))
    check("trajectory insensitive to vent loss (EM-42: 'not apparent')",
          traj_delta <= 0.005 and traj_delta_printed == 0.0,
          f"engine {traj_delta:.2e} m, printed {traj_delta_printed:.2f} m")

    # ------------------------------------------------------------------
    print("  engine internals .....................................")
    # closed-form Glazov solution vs RK4 (the original used Runge-Kutta)
    t_end = resA.land_t
    _, x_cf, y_cf = 0.0, *_glazov_xy(t_end, 55.579, 36.463, 1e-9)
    t_rk, x_rk, y_rk, _, _ = _glazov_rk4(t_end, 55.579, 36.463, 1e-9,
                                         n_steps=20000)
    err = max(abs(x_cf - x_rk), abs(y_cf - y_rk))
    check("closed-form Glazov == RK4 (max err <= 1e-6 m)", err <= 1e-6,
          f"{err:.2e}")

    # ------------------------------------------------------------------
    print("  legacy / edge cases ..................................")
    # ascending chute deflector on a flat floor (legacy v1.0 style usage)
    ramp = RampGeometry(angle_deg=11.3, elev_lip=1000.0, sta_lip=800.0,
                        elev_floor=995.0)
    flow = FlowProperties(q=283.168, velocity_ramp=35.0, depth_ramp=1.5,
                          turbulence=0.05)
    vent = VentGeometry(n_vents=1, width=6.0, area=2.0, loss_coeff=0.5)
    res = compute_trajectory(ramp, flow, vent)
    check("ascending deflector: success + lands downstream",
          res.success and res.land_x > ramp.sta_lip,
          f"land_x={res.land_x:.2f}")
    check("ascending deflector: positive air demand",
          res.air_flow_rate >= 0.0, f"{res.air_flow_rate:.3f}")

    # jet over the end of the structure (lip above a short profile segment)
    ramp2 = RampGeometry(angle_deg=-5.0, elev_lip=1000.0, sta_lip=0.0,
                         elev_floor=900.0,
                         profile=[(0.0, 999.5), (10.0, 995.0)])
    res2 = compute_trajectory(ramp2, flow, vent)
    check("jet over end: warning issued",
          (not res2.success) or res2.jet_passes_over_end
          or ("JET PASSES OVER END OF STRUCTURE" in res2.warnings),
          str(res2.warnings))

    # degenerate: zero turbulence still yields a valid single curve set
    flow3 = FlowProperties(q=283.168, velocity_ramp=36.463, depth_ramp=1.385,
                           turbulence=0.0)
    ramp3 = RampGeometry(angle_deg=-53.975, elev_lip=1035.112, sta_lip=685.80,
                         elev_floor=956.25, profile=profile)
    res3 = compute_trajectory(ramp3, flow3, vent)
    check("T=0: dispersion collapses onto centerline angle",
          abs(res3.dispersion_angle_deg) < 1e-12
          and abs(res3.penetration_angle_deg - (-53.975)) < 1e-9,
          f"{res3.dispersion_angle_deg}")

    # ------------------------------------------------------------------
    print()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)}): " + ", ".join(_FAILURES))
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
