#!/usr/bin/env python3
"""Pilot validation: WS77 Python port vs GLENOUT reference (Glen Canyon).

Produces a per-station deviation CSV + summary JSON for the SWB paper nucleus.
Run from em_py directory of the SWB repo.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from em_data import read_geometry_file, read_ws_output
from em_ws77 import compute_profile

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data", "DATA")
OUT_DIR = "/home/z/my-project/swb_work"


def main():
    g = read_geometry_file(os.path.join(DATA, "GLENIN"))
    ref = read_ws_output(os.path.join(DATA, "GLENOUT"))
    res = compute_profile(g, egl_calibration=ref.egl_initial)

    rows = []
    d_errs, v_errs, egl_errs = [], [], []
    n = min(len(res.rows), len(ref.profile_rows))
    for r, ref_r in zip(res.rows[:n], ref.profile_rows[:n]):
        d_err = r["depth"] - ref_r.depth
        v_err = r["velocity"] - ref_r.velocity
        v_rel = v_err / max(ref_r.velocity, 0.1)
        egl_err = r["egl"] - ref_r.energy_grade
        d_errs.append(abs(d_err))
        v_errs.append(abs(v_rel))
        egl_errs.append(abs(egl_err))
        rows.append({
            "sta": r["sta"],
            "depth_py": round(r["depth"], 4), "depth_ref": round(ref_r.depth, 4),
            "depth_err_m": round(d_err, 4),
            "V_py": round(r["velocity"], 3), "V_ref": round(ref_r.velocity, 3),
            "V_rel_err_pct": round(100.0 * v_rel, 2),
            "EGL_py": round(r["egl"], 3), "EGL_ref": round(ref_r.energy_grade, 3),
            "EGL_err_m": round(egl_err, 4),
            "profile_py": r["profile"],
        })

    def stats(vals, scale=1.0):
        s = sorted(vals)
        n_ = len(s)
        return {
            "max": round(max(s) * scale, 4),
            "median": round(s[n_ // 2] * scale, 4),
            "mean": round(sum(s) / n_ * scale, 4),
        }

    summary = {
        "case": "Glen Canyon left spillway tunnel (GLENIN/GLENOUT, Q=283.168 cms, 27 stations)",
        "egl_initial_py": round(res.egl_initial, 3),
        "egl_initial_ref": round(ref.egl_initial, 3),
        "depth_err_m": stats(d_errs),
        "velocity_rel_err_pct": stats(v_errs, 100.0),
        "egl_err_m": stats(egl_errs),
        "n_stations": n,
        "worst_station_by_V": max(rows, key=lambda r: r["V_rel_err_pct"])["sta"],
        "worst_V_rel_err_pct": max(r["V_rel_err_pct"] for r in rows),
    }

    # CSV
    import csv
    csv_path = os.path.join(OUT_DIR, "pilot_ws77_vs_glenout.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # JSON
    json_path = os.path.join(OUT_DIR, "pilot_ws77_summary.json")
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nCSV: {csv_path}\nJSON: {json_path}")


if __name__ == "__main__":
    main()
