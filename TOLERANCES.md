# Numerical acceptance gates used by the SWB v1.2 regression suites

**Status:** repository documentation — commit with the v1.2.1 hygiene release.
**Answers:** Reviewer 1 point 1 (exact tolerance thresholds ε_rel, ε_abs and
rounding-difference handling). All values are read directly from the test
files — this document restates them so the paper and the code cannot drift.

## 1. WS77 v1.1 gate (test_ws77_v11.py, vs archived GLENOUT reference)

| Quantity | Symbol | Threshold |
|---|---|---|
| Velocity, relative | ε_rel(V) | ≤ 5.0 % per station |
| Depth, relative | ε_rel(y) | ≤ 5.0 % per station |
| Depth, absolute | ε_abs(y) | ≤ 0.05 m per station (accepts either the 5 % or the 0.05 m criterion) |
| Internal geometry checks | ε_rel(A) | ≤ 1 % (circular), ≤ 2 % (composite) |
| Colebrook–Manning n check | ε_rel(n) | ≤ 3 % |
| Worst observed deviation (v1.1) | — | velocity 1.06 % (27/27 stations pass) |

**Rounding handling:** comparisons run on engine floats against the archived
reference values; no rounding is applied before the gate (rounding would mask
divergence). The printed 2-decimal resolution of the 1990 output is treated as
*print resolution*, not as tolerance — the trajectory tables below carry
tighter engine-level thresholds than the printed grid.

## 2. TRAJ v1.2 gates (test_traj_v12.py, vs EM-42 Appendix D p. 127)

| Quantity | Threshold |
|---|---|
| Air flow Q_air (run A) | ≤ 2 % relative to 27.50 m³/s (observed 27.446, −0.11 %) |
| Vent pressure drop dP, run A | prints ".006": 0.0055 ≤ dP < 0.0065 m H₂O (observed 0.00612) |
| Vent pressure drop dP, run B (K=1.2) | prints ".007": 0.0066 ≤ dP < 0.0078 m H₂O (observed 0.00718) |
| Landing station / elevation | ≤ ±0.10 m each (observed 688.433 / 1031.189 vs 688.44 / 1031.18) |
| Trajectory tables (lower nappe 1 & 2) | max pointwise diff ≤ 0.06 m |
| Top-nappe table | max pointwise diff ≤ 0.08 m (print-grid ambiguity band) |
| Run A→B trajectory sensitivity | engine ≤ 0.005 m; printed tables identical (EM-42: "not apparent") |
| Closed-form Glazov vs RK4 | max err ≤ 1e-6 m |
| Iteration convergence | ≤ 20 iterations, pressure tolerance 0.05 Pa (`_PRESSURE_TOL_PA`) |

## 3. Blue Mesa case gate

| Quantity | Threshold |
|---|---|
| 65 interpolated trajectory points | worst absolute deviation ≤ 0.02 m vs the original binary's printed table |
| Vent pressure drop dP | **known limit:** engine 0.00796 vs printed .006 — recorded, not tuned away. Closure test executed 2026-11-23 (six shadow runs R1–R6): documented legacy PF/BV factors excluded numerically and structurally; deviation localized in the reconstructed vent/cavitation term; the 2026-11-23 cavitation-formula session identifies a parameter-free candidate reading (jet vertical projection) that restores the printed .006 at Blue Mesa while preserving both Glen gates (adoption pending author signal) (see `POST1990_DELTA.md` rows 2–3, `CLOSURE_TEST_PLAN.md` §4) |

## 4. Sensitivity note (Reviewer 1-1, second part)

The sensitive downstream derivative flagged by the reviewer is the cavitation
index σ = (p − p_v)/(½ρV²), whose velocity term enters squared: a 1 % velocity
rounding difference becomes ≈ 2 % in σ⁻¹ at boundary-layer inception. The
gates above are set wide enough (5 %/0.05 m) that a *rounding* difference
cannot pass while a *code divergence* fails: any divergence that changes σ
classification (flow σ vs incipient σr) exceeds the gate by construction. The
per-station pass/fail list is printed by the suites (`failures` array with
station, v_err_pct, d_err), so a marginal pass is inspectable, not silently
absorbed.
