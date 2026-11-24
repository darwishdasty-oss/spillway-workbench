# Blue Mesa TRAJ case: evidence appendix and "first numerical record" protocol

**Status:** repository documentation — commit with the v1.2.1 hygiene release.
**Answers:** Reviewer 3 annotation 9 ("What source provides this table?") and
Reviewer 4 point 9 ("the claim regarding the 'first numerical reproduction' of
the Blue Mesa table results requires more precise documentation and evidence").

## 1. What the claim is (exact wording discipline)

SWB v1.2 claims: *the Blue Mesa aerator trajectory printed by the original
April-1990 TRAJ binary was reproduced at all 65 interpolated points within
0.02 m*. The supporting claim in the paper — "the first numerical record of
that table" — means precisely: **no numerical record of this trajectory table
was located in the open literature as of the search date below**; the table
itself existed only as printed output of the original binary run on the
author's machine.

## 2. Oracle-run provenance (answers "what source provides this table?")

| Item | Value |
|---|---|
| Program executed | `TRAJ.EXE` (USBR Cavitation Programs, June 1987 distribution; bundled unmodified in `em_py/sample_data/`, see NOTICE.md) |
| Execution environment | DOS emulation (DOSBox) on the author's Windows machine |
| Geometry input | `BLUEMESA.GEO` (as-built Blue Mesa spillway geometry, GLENIN format) — archived with this repository |
| Aerator inputs | ramp lip station/elevation, ramp angle, vent area × count, vent width, vent loss coefficient, flow properties (Q, depth, velocity, turbulence) — **listed verbatim from the original program's vent echo** (archived byte-wise in the campaign evidence package `traj.zip`, MD5-verified 2026-11-23; matches the engine input verdict JSON 11/11): ramp lip station 416.18, lip elevation 2237.684, ramp angle 53.975°, vent opening 0.835, vent width 0.914, vent loss coefficient 1.0, **vent count = 1**, flow Q = 28.317, turbulence T = 0.0302, flow depth 0.497, flow velocity 23.143 (values as printed by the original program) |
| Original output | 23-row printed table (22 grid points + landing row); header reports ramp width 2.46 m (from continuity), air flow 7.77 m³/s, vent pressure drop .006 |
| Archived evidence | console transcript of the original run — **to be deposited as `em_py/sample_data/BLUEMESA_TRAJ_ORIGINAL.txt` in the v1.2.1 release** |
| Engine output | `em_py.em_traj` v1.2 on identical inputs; 65 interpolated points within 0.02 m; vent pressure drop computed 0.00796 vs printed .006 — **the known limit, now characterized by the executed closure test (2026-11-23, six shadow runs R1–R6): a localized deviation in the reconstructed vent/cavitation term, with the documented legacy PF/BV pressure factors excluded numerically and structurally** (PF structurally inapplicable — the vent echo confirms a single opening; the remaining factor explains 1.4 % of the deviation; see `POST1990_DELTA.md` rows 2–3 and `closure_test/CLOSURE_TEST_PLAN.md` §4). The cavitation-formula session of 2026-11-23 further shows the deviation is removable by a parameter-free geometric reading of the App. D cavity section (jet vertical projection, a_cav = width·h0/cos θ) that restores the printed .006 with air 7.776 vs printed 7.77 — pending the author's engine decision. |

## 3. Literature-search protocol (answers "first numerical record")

Search performed 2026-11-23; to be re-run on the date of any future submission
and re-stated with that date.

| Database / source | Query set | Result |
|---|---|---|
| Google Scholar | "Blue Mesa" spillway trajectory; "Blue Mesa" aerator cavitation; Blue Mesa spillway *Falvey*; tunnel spillway aerator "Blue Mesa" | No numerical trajectory table located |
| USBR sites (usbr.gov TSC + Hydraulic Laboratory reports HL/PAP series) | "Blue Mesa" + cavitation/aerator/trajectory; EM-42 companion pages | Narrative damage history only; no trajectory table |
| Wahl & Falvey 2022 (Water 14(8):1256) + HL-2019-03 | Blue Mesa examples | Appendix A lists Blue Mesa among retrofitted tunnel spillways; no printed trajectory table |
| IAHR / dam-safety proceedings with Glen Canyon 1983 damage follow-ups | Blue Mesa spillway retrofit | Descriptions of retrofit; no trajectory table |
| Classic textbooks citing EM-42 appendix examples | Falvey-citing literature | No Blue Mesa trajectory table found |

**Negative-claim discipline:** the statement in any future text must read
"no numerical record of this table was located in the open literature as of
2026-11-23 (search protocol archived with the repository)" — never an
unqualified "first".

## 4. Reproduction protocol (independent check anyone can run)

1. Download the release archive; the original binaries and `DATA/` are bundled
   (public domain, NOTICE.md).
2. Run `TRAJ.EXE` under any DOS emulator with `BLUEMESA.GEO` and the aerator
   inputs listed in §2 → obtain the 23-row printed table.
3. Run the engine headless with the same inputs (see module `__main__`
   example in `em_py/em_traj.py`) → obtain the 65 interpolated points.
4. Compare: worst absolute deviation ≤ 0.02 m across all 65 points.

## 5. Outstanding items on the author

- [ ] Deposit the console transcript of the original Blue Mesa run
      (`BLUEMESA_TRAJ_ORIGINAL.txt`) in the v1.2.1 release — the single
      missing evidence artifact. (Interim status: the run screenshots are
      archived byte-wise in the campaign evidence package `traj.zip`,
      MD5-verified 2026-11-23.)
- [x] List the aerator input block verbatim in §2 — done 2026-11-23 from
      the archived vent echo (traj_006–013).
- [x] Confirm vent count/width for Blue Mesa — done 2026-11-23: the vent
      echo confirms **one opening** (width 0.914, loss coefficient 1.0),
      which structurally excludes the multi-vent PF factor; the PF/BV
      closure test was executed the same day (see `POST1990_DELTA.md`
      rows 2–3).
