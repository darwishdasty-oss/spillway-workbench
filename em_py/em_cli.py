"""
em_cli.py - Command-line interface for batch processing.

Allows running WS77, TRAJ, ECAVNO, CONSTP, DINDX, CONVT, CKDATA from the
command line without launching the GUI.

Usage examples:
    python -m em_cli ws77 --input sample_data/DATA/GLENIN --output report.pdf
    python -m em_cli ws77 --input sample_data/DATA/GLENIN --output results.json
    python -m em_cli convt --value 283.168 --from cms --to cfs
    python -m em_cli ckdata --input sample_data/DATA/GLENIN
    python -m em_cli traj --input sample_data/DATA/GLENIN --sta 720
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from typing import List

from em_data import read_geometry_file, read_ws_output
from em_ws77 import compute_profile
import em_convert as ec
import em_ckdata as ck
import em_traj as et
import em_ecavno as ee
import em_constp as ep
# dindx loaded lazily in _dindx
from em_report import make_pdf_report


def _ws77(args):
    g = read_geometry_file(args.input)
    egl = None
    if args.egl:
        egl = float(args.egl)
    elif args.calibrate and os.path.exists(args.calibrate):
        ref = read_ws_output(args.calibrate)
        egl = ref.egl_initial
    res = compute_profile(g, egl_calibration=egl)
    if not res.success:
        print(f"ERROR: {res.error_message}", file=sys.stderr)
        return 1
    if args.output:
        ext = os.path.splitext(args.output)[1].lower()
        if ext == ".json":
            payload = {
                "egl_initial": res.egl_initial,
                "success": res.success,
                "rows": res.rows,
            }
            with open(args.output, "w") as f:
                json.dump(payload, f, indent=2, default=float)
            print(f"JSON written: {args.output}")
        elif ext == ".pdf":
            make_pdf_report(g, res, args.output)
            print(f"PDF written: {args.output}")
        elif ext == ".csv":
            import csv
            with open(args.output, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=res.rows[0].keys())
                w.writeheader()
                w.writerows(res.rows)
            print(f"CSV written: {args.output}")
        else:
            print(f"Unknown output format: {ext}", file=sys.stderr)
            return 1
    else:
        print(f"STA         invert      depth       V        EGL         sigma       profile")
        for r in res.rows:
            print(f"{r['sta']:8.1f}  {r['invert']:8.3f}  {r['depth']:7.3f}  "
                  f"{r['velocity']:6.2f}  {r['egl']:8.3f}  {r['sigma']:8.3f}  {r['profile']}")
    return 0


def _convt(args):
    result = ec.convert_value(args.value, args.from_unit, args.to_unit)
    if isinstance(result, tuple):
        val, unit = result
        print(f"{args.value} {args.from_unit} = {val:.6g} {unit}")
    else:
        print(f"{args.value} {args.from_unit} = {result:.6g} {args.to_unit}")
    return 0


def _ckdata(args):
    g = read_geometry_file(args.input)
    res = ck.check_data(g, args.input.split("/")[-1])
    print(f"CKDATA: {g.title}")
    print(f"  Stations: {len(g.stations)}")
    print(f"  Q = {g.q} cms, y0 = {g.y0} m, k_s = {g.k_s*1000:.2f} mm")
    print(f"  Issues found: {len(res.checks)}")
    for w in res.checks[:10]:
        print(f"    - {w}")
    if not res.checks:
        print("  OK -- no issues")
    return 0 if not res.has_errors else 1


def _traj(args):
    from em_traj import RampGeometry, FlowProperties, VentGeometry, compute_trajectory
    from em_data import read_geometry_file
    from em_ws77 import compute_profile
    g = read_geometry_file(args.input)
    res = compute_profile(g)
    target = args.sta
    y_at = min(res.rows, key=lambda r: abs(r["sta"] - target))
    V = y_at["velocity"]
    y = y_at["depth"]
    ramp = RampGeometry(angle_deg=11.3, elev_lip=y_at["invert"] + y, sta_lip=target,
                         elev_floor=y_at["invert"])
    flow = FlowProperties(q=g.q, velocity_ramp=V, depth_ramp=y, turbulence=0.05)
    vent = VentGeometry(n_vents=1, width=6.0, area=2.0, loss_coeff=0.5)
    traj_res = compute_trajectory(ramp, flow, vent)
    print(f"TRAJ at sta {target:.1f}:")
    print(f"  Approach V = {V:.2f} m/s, y = {y:.3f} m")
    print(f"  Land x: {traj_res.land_x:.2f} m, land t: {traj_res.land_t:.3f} s")
    print(f"  Max height: {traj_res.max_height:.2f} m")
    print(f"  Air velocity required: {traj_res.air_velocity_required:.1f} m/s")
    print(f"  Air flow rate: {traj_res.air_flow_rate:.4f} cms")
    return 0


def _ecavno(args):
    print(f"ECAVNO: design equal cavitation number to sigma={args.sigma} at sta={args.sta}")
    print("  (See ECAVNO menu in GUI for full iterative design)")
    return 0


def _constp(args):
    from em_constp import compute_constp
    g = read_geometry_file(args.input)
    res = compute_constp(g, distribution='S' if args.kind == "sinusoidal" else 'T')
    print(f"CONSTP ({args.kind}):")
    print(f"  Distribution: {res.distribution}")
    print(f"  N points: {len(res.points)}")
    print(f"  Max piez head: {res.max_piez_head:.3f}")
    print(f"  Min piez head: {res.min_piez_head:.3f}")
    print(f"  Q: {res.Q:.3f} cms")
    return 0


def _dindx(args):
    from em_dindx import HydrographPoint, DEFAULT_DAMAGE_COEFFS
    # Read a simple hydrograph file: one (t, Q) pair per line
    points = []
    with open(args.input) as f:
        for line in f:
            parts = line.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    t = float(parts[0])
                    q = float(parts[1])
                    points.append(HydrographPoint(t=t, q=q))
                except ValueError:
                    continue
    if not points:
        print("No hydrograph points parsed from", args.input, file=sys.stderr)
        return 1
    print(f"DINDX: {len(points)} hydrograph points")
    for p in points[:5]:
        # Default fit coefficients
        coeffs = DEFAULT_DAMAGE_COEFFS["1/2_in"]
        # C and D
        C, D = coeffs
        sigma = 1.0  # placeholder
        damage = q * 0.001
        print(f"  t={p.t:6.1f}  Q={p.q:8.2f}  damage_proxy={damage:.4f}")
    return 0

    res = compute_damage_index(d)
    print(f"DINDX: {len(res.curve)} points")
    for r in res.curve[:5]:
        print(f"  sigma={r.sigma:.3f}  damage={r.damage:.4f}")
    return 0


def main():
    p = argparse.ArgumentParser(prog="em_cli", description="EM-Py command-line interface")
    sub = p.add_subparsers(dest="tool", required=True)

    # ws77
    pw = sub.add_parser("ws77", help="Run WS77 water surface profile")
    pw.add_argument("--input", required=True)
    pw.add_argument("--output", help="Output file (.json, .csv, or .pdf)")
    pw.add_argument("--egl", help="Override initial EGL (m)")
    pw.add_argument("--calibrate", help="Path to GLENOUT reference for EGL calibration")
    pw.set_defaults(func=_ws77)

    # convt
    pc = sub.add_parser("convt", help="Unit conversion")
    pc.add_argument("--value", type=float, required=True)
    pc.add_argument("--from", dest="from_unit", required=True)
    pc.add_argument("--to", dest="to_unit", required=True)
    pc.set_defaults(func=_convt)

    # ckdata
    pk = sub.add_parser("ckdata", help="Validate a geometry file")
    pk.add_argument("--input", required=True)
    pk.set_defaults(func=_ckdata)

    # traj
    pt = sub.add_parser("traj", help="Compute aerator jet trajectory")
    pt.add_argument("--input", required=True)
    pt.add_argument("--sta", type=float, default=720.0)
    pt.add_argument("--jump-height", type=float, default=0.5)
    pt.set_defaults(func=_traj)

    # ecavno
    pe = sub.add_parser("ecavno", help="Design equal cavitation index")
    pe.add_argument("--input", required=True)
    pe.add_argument("--sigma", type=float, default=0.2)
    pe.add_argument("--sta", type=float, default=720.0)
    pe.add_argument("--q", type=float, default=None)
    pe.set_defaults(func=_ecavno)

    # constp
    ps = sub.add_parser("constp", help="Controlled pressure")
    ps.add_argument("--input", required=True)
    ps.add_argument("--kind", choices=["sinusoidal", "triangular"], default="sinusoidal")
    ps.add_argument("--amplitude", type=float, default=0.05)
    ps.add_argument("--wavelength", type=float, default=1.0)
    ps.set_defaults(func=_constp)

    # dindx
    pd = sub.add_parser("dindx", help="Compute damage index")
    pd.add_argument("--input", required=True)
    pd.set_defaults(func=_dindx)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
