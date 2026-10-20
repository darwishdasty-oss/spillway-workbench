#!/usr/bin/env python3
"""Headless regression test for the WS77 v1.1 engine (no GUI required).

Validates the rewritten standard-step solver against the original USBR
GLENOUT reference output for the Glen Canyon left spillway tunnel sample,
using the v1.1 acceptance gate agreed for the SWB paper:
    velocity error <= 5 %  and  depth error <= 5 % (or <= 0.05 m)

Run from the repository root:   python3 test_ws77_v11.py
(The GUI suite in test_swb.py covers the interface; this file covers the
hydraulic engine and runs anywhere, including CI.)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "em_py"))

from em_data import read_geometry_file, read_ws_output
from em_ws77 import (compute_profile, section_geometry, _circular, _composite,
                     colebrook_manning_n)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "em_py", "sample_data", "DATA")
TOL_V_PCT = 5.0
TOL_D_PCT = 5.0
TOL_D_ABS = 0.05


def approx(a, b, tol):
    return abs(a - b) <= tol * max(1.0, abs(b))


def test_section_geometry():
    # circular section: radius 6.25 m at depth 1.826 -> A ~= 11.105 m2
    A, P, _b = _circular(6.25, 1.826)
    assert approx(A, 11.105, 0.01), f"circular area {A}"
    # composite (Glen Canyon sta 637): W=22.372, RADCL=12.655, Rup=2.944,
    # Rlow=2.082, T=1.830 at depth 0.7437 -> A ~= 13.80 m2  (GLENOUT: Q/V)
    A, P, b = _composite(22.372, 12.655, 2.944, 2.082, 1.830, 0.7437)
    assert approx(A, 13.80, 0.02), f"composite area {A}"
    print("  section geometry ......... OK")


def test_fiction_model():
    # Colebrook n for k_s = 0.3048 mm, R = 0.832 m, Re = 1.37e8 -> ~0.0122
    n = colebrook_manning_n(0.0003048, 0.832, 4 * 0.832 * 41.2 / 1.3e-6)
    assert approx(n, 0.0122, 0.03), f"colebrook n {n}"
    print("  Colebrook friction ....... OK")


def test_profile_gate():
    g = read_geometry_file(os.path.join(DATA, "GLENIN"))
    ref = read_ws_output(os.path.join(DATA, "GLENOUT"))
    res = compute_profile(g)          # fully independent start (no reference)
    n = min(len(res.rows), len(ref.profile_rows))
    failures = []
    for r, ref_r in zip(res.rows[:n], ref.profile_rows[:n]):
        v_err_pct = 100.0 * abs(r["velocity"] - ref_r.velocity) / ref_r.velocity
        d_err = abs(r["depth"] - ref_r.depth)
        d_ok = (100.0 * d_err / ref_r.depth <= TOL_D_PCT) or (d_err <= TOL_D_ABS)
        if not (v_err_pct <= TOL_V_PCT and d_ok):
            failures.append((r["sta"], v_err_pct, d_err))
    assert not failures, f"gate failures: {failures}"
    print(f"  v1.1 gate vs GLENOUT ..... OK ({n}/{n} stations within gate, "
          f"independent start)")


if __name__ == "__main__":
    print("test_ws77_v11: WS77 engine regression tests")
    test_section_geometry()
    test_fiction_model()
    test_profile_gate()
    print("ALL TESTS PASSED")
