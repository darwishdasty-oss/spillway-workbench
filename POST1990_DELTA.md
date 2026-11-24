# Post-1990 Delta: EM-Py versus the documented USBR corrections (HL-2019-03)

**Status:** repository documentation — commit with the v1.2.1 hygiene release.
**Purpose:** answer the SoftwareX review critique that SWB/EM-Py "reimplements
tools that are no longer state-of-the-art without acknowledging bug fixes and
functional improvements made since 1990" (Reviewer 3, SOFTX-D-26-01506), by
documenting, engine by engine, exactly which 1990 behaviors EM-Py reproduces
and which post-1990 USBR corrections exist.

## 1. Positioning statement (the one paragraph)

EM-Py is a **deliberately 1990-faithful reference implementation** of the USBR
Cavitation Programs (Falvey, FORTRAN 77, June 1987 / April 1990). Its design
goal is forensic: to reproduce the printed behaviour of the original binaries
so that the archived monograph tables and benchmark cases remain executable
and testable on modern platforms. It is **not** a claim to be the state of the
art. The USBR's own modern tool, **SpillwayPro** (Hydraulic Laboratory Report
HL-2019-03, Wahl, Frizell & Falvey, April 2019; Wahl & Falvey, *Water* 14(8):1256,
2022), is the state of the art inside the agency: it reimplements the same
program family on an Excel/VBA platform **and documents a list of corrections
and improvements to the original FORTRAN programs**. The table below maps every
documented correction onto EM-Py v1.2, so a reader can see at a glance which
1990 behaviours are reproduced on purpose and where the two tools differ.

## 2. Lineage (corrected diagram)

```
USBR Cavitation Programs (Falvey, FORTRAN 77, 1987/1990, diskette source included)
        │                                   │
        │ recompiled by USBR during         │
        │ SpillwayPro development           │
        ▼                                   ▼
   EM-Py (2026, Python, 1990-faithful)   SpillwayPro (2019/2022, Excel/VBA,
        │                                 USBR's current tool: corrected
        │                                 equations + new capabilities)
        └────────────►  SWB (Python, 2026)  ◄────────────┘
              unified workbench: design ↔ analysis
```

Note: the diskettes distributed with the printed monograph **did include
FORTRAN source code**; USBR recompiled that source during SpillwayPro's
development (per HL-2019-03) and the usbr.gov site now hosts SpillwayPro in
place of the original EM42 programs. EM-Py was **not** built from
SpillwayPro's VBA; its decoding sources were (a) the EM-42 monograph text and
appendices and (b) the behaviour of the original DOS binaries (prompt
protocol, embedded strings, printed outputs), with the WS77 section-geometry
transcription cross-checked against the COMP function **as preserved in
SpillwayPro's VBA** (reviewed by Wahl against the FORTRAN) — see
`em_py/em_ws77.py` module header and `_composite()` docstring.

## 3. Delta table — HL-2019-03 "Differences from the EM42 FORTRAN Programs" vs EM-Py v1.2

| # | HL-2019-03 documented change | Engine | EM-Py v1.2 status |
|---|---|---|---|
| 1 | Transition loss `0.1·(V2²−V1²)/2g` was applied by the original WS77 **at every station** even when the section did not vary (overestimating head losses); **corrected** in SpillwayPro | WS77 | **Reproduced as 1990 behaviour by design** (`TLF = 0.1` applied at every reach; `em_py/em_ws77.py` cites HL-2019-03 in the constant definition). The known-bias is accepted because the WS77 validation target is the archived 1990 reference output GLENOUT (27/27 stations, worst velocity deviation 1.06%). A corrected-loss variant is a possible future option flag, off by default. |
| 2 | Trajectory: **"PF" factor** (multiplied the pressure factor Cn of Eqs. 5.1/5.2 by 4 when more than one air vent existed; HL-2019-03: "the effect was backward from the correct adjustment") — **eliminated** in SpillwayPro | TRAJ | **Not implemented** (EM-Py computes Cn directly from the vent pressure difference). Consequence: on multi-vent cases EM-Py reproduces the 1990 trajectory/pressure iteration; SpillwayPro applies the corrected adjustment. **Candidate explanation for the Blue Mesa vent-pressure deviation — tested and refuted** (closure test executed 2026-11-23, six shadow runs R1–R6, zero repository changes): *structurally* excluded at Blue Mesa (the original run's vent echo confirms a single opening, and PF activates only on multiple vents) and *numerically* nil at Glen (activating the factors moved dP by ≤ 2×10⁻⁶ m, R2/R4 vs R1/R3). **Localization:** the deviation sits in the *reconstructed vent/cavitation term*, not in the trajectory path — the duct-loss (stream) term matches between the two cases (0.00532 vs 0.00542 m) while the full excess sits in the reconstructed term (0.00078 vs 0.00253 m), whose cavity cross-section is 6.3× smaller at Blue Mesa (1.224 vs 7.766 m²; v_cav 3.53 → 6.36 m/s). Known-limit wording adopted (author signal, 2026-11-23): *a localized deviation in the reconstructed vent-pressure (cavitation) term, with the documented legacy PF/BV pressure factors excluded numerically and structurally*. See `closure_test/CLOSURE_TEST_PLAN.md` §4 and the campaign evidence package (`closure_test_results.txt`, `dp_split_diagnostic.txt`). |
| 3 | Trajectory: **"BV/B" factor** (reduced the effective pressure difference across the jet when the vent slot width ≪ chute width; "insufficient experimental evidence to validate its use") — **eliminated** in SpillwayPro | TRAJ | **Not implemented** (same rationale as row 2). **Closure test 2026-11-23: refuted as an explanation of the Blue Mesa deviation** — with the BV/B factor active at Blue Mesa (k = vent width / ramp width = 0.914/2.46 = 0.371, i.e. Cn −63 %; run R6, PF structurally excluded), dP moved 0.007963 → 0.007935: the factor accounts for **1.4 % of the 0.001963 m excess** over the printed .006 — the direction is correct but numerically negligible at this scale. Any candidate vent-term formula must satisfy the dual constraint measured by the plan (Glen prints .006/.007 preserved **and** Blue Mesa dP lands in [.0055, .0065)); note that removing the term entirely fails both (Glen would print .005), so the original program used a different formula, not no formula. **Cavitation-formula session 2026-11-23 (shadow copy, zero repository changes):** four source-grounded readings of the App. D Bernoulli sentence tested against the dual gate. The SpillwayPro corrected form (pure eq 5.5, no cavity term) fails both sites (.011); the cavity-gap reading fails both (.088/.039); the v1.2 reading (jet section = width·h0) fails Blue Mesa (.008). Reading the section as the jet's vertical projection (a_cav = width·h0/cos θ_lip; same 53.975° ramp angle at both dams, zero free parameters) passes the full dual gate — Glen .006 (0.005607) / .007 (0.006673) preserved, Blue Mesa lands on .006 (0.006301) with air 7.776 vs printed 7.77, printed trajectory tables shift ≤ 0.0084 m (inside the 0.02 m evidence gate). Honest margins (recorded per author signal, 2026-11-23): the Glen passes under this reading are thin — Glen A sits 0.000107 above the .0055 floor and Glen B 0.000073 above the .0066 floor, whereas the correction itself moves dP by 0.000510 — so any future v1.3 adoption must state these margins explicitly. Engine adoption is an author decision (session card: `SWB_CavForm_Session_2026-11-23/00_SESSION_CARD_AR.md`). |
| 4 | Controlled-pressure program: **erroneous equations in EM-42 itself** (Eqs. 4.46, 4.48, 4.49, C.12, C.14, C.15 and the unnumbered eqs. pp. 52–53 / 113–114), embedded in the original program; **corrected equations published** in HL-2019-03 Table 2 | CONSTP | EM-Py implements the EM-42 documented algorithm (Section 5.3) at documentation level; **any production use of CONSTP should apply the HL-2019-03 Table 2 corrected equations** — flag to be added in a future version. |
| 5 | Controlled-pressure program: arc-distance / radius-of-curvature **scaling misreported** in the original; **corrected** | CONSTP | Not reproduced deliberately; see row 4 caveat. |
| 6 | Controlled-pressure program: **Simpson's-rule integration error** in the original; **corrected** | CONSTP | See rows 4–5. |
| 7 | Water-surface profile: cross-sections must be entered normal to bed slope (vertical-plane option of the original removed) | WS77 | N/A — EM-Py reads the GLENIN format, which uses bed-normal input. |
| 8 | Profile: Froude number added to output (two variants) | WS77 | EM-Py computes a Froude column as an audit extra (not in the 1990 printout) — noted as such in the output schema. |
| 9 | Profile: **roll-wave detection** added | WS77 | **Not implemented** (post-1990 capability; SpillwayPro-only). |
| 10 | Profile: **stream power** added | WS77 | Not implemented (post-1990 capability). |
| 11 | Profile: **streamline-curvature method revised** (channel-slope effects + curvature variation with distance from bed) | WS77 | EM-Py uses the EM-42 curvature treatment as documented in the monograph; the revised method is a SpillwayPro improvement (Shasta-driven). |
| 12 | Trajectory: ramp-angle / ramp-height **input convention changed** (deviation above bed slope; perpendicular lip height) | TRAJ | N/A for validation (EM-Py accepts the original convention and the SWB signed convention; both documented in the module docstring). |
| 13 | Trajectory: relative ramp-height adjustment (EM-42 Fig. 5-3) incorporated automatically | TRAJ | Implemented (adjustment applied inside the engine). |
| 14 | Trajectory: **stream power at jet impact** + thrust forces added (Oroville-driven) | TRAJ | Not implemented (post-1990 capability). |
| 15 | Turbulence intensity: early spreadsheet versions differed from the EM-42 FORTRAN formula; **proper formula restored** (Ti = 0.25·√f, Colebrook–White per Henderson 1966 with boundary-layer thickness) | WS77/damage chain | EM-Py uses the EM-42 formula family; no divergence to document. |

**Summary:** of the 15 documented deltas, EM-Py reproduces 1990 behaviour on
purpose for rows 1–3 (the validation target is the 1990 oracle), inherits no
divergence for rows 7–8, 12–13, 15, and does not implement the post-1990
capability additions (rows 9–10, 14) or the CONSTP corrections (rows 4–6),
which are documented here and flagged for future optional modes.

## 4. How this file answers the review

- "without acknowledging bug fixes and functional improvements made since
  1990" → this file is the acknowledgment, with per-engine mapping.
- "not really independent, since the printed tables came from the execution
  of the original source code" → accepted: the monograph tables and the
  binaries are **one lineage in two renderings** (typeset vs executed). The
  verification design is described honestly in
  `repo_files/VALID_BOUNDS_AND_ORACLES.md`, which adds genuinely independent
  legs (closed-form checks, published laboratory data, and cross-runs against
  SpillwayPro's published example applications).
- "What source code was used to create EM-Py?" → §2 provenance statement:
  EM-42 text + original binaries' behaviour; section geometry cross-checked
  against SpillwayPro's preserved VBA COMP; **no SpillwayPro VBA executed or
  ported**.

## 5. References

1. Falvey, H. T. (1990). *Cavitation in Chutes and Spillways*. USBR Engineering
   Monograph No. 42.
2. Wahl, T. L., Frizell, K. W., Falvey, H. T. (2019). *SpillwayPro — Tools for
   Analysis of Spillway Cavitation and Design of Chute Aerators*. USBR
   Hydraulic Laboratory Report HL-2019-03 (a supplement to EM-42).
3. Wahl, T. L., Falvey, H. T. (2022). *SpillwayPro: Integrated water surface
   profile, cavitation and aerator analysis tools*. Water, 14(8), 1256.
4. Falvey, H. T. (1987). *Cavitation of Bureau of Reclamation Spillways*.
   USBR (the June-1987 DOS program distribution bundled in `em_py/sample_data/`).
