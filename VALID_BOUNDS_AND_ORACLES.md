# Validity bounds, verification design, and terminology (SWB v1.2.1)

**Status:** repository documentation — commit with the v1.2.1 hygiene release.
**Answers:** Reviewer 1 points 2 and 3; Reviewer 3 annotations 3, 4, 12, 13,
14; Reviewer 4 points 4 and 10.

## 1. Valid geometric and hydraulic bounds of SWB (Reviewer 1-3)

SWB's engines re-derive and reimplement 1-D standard-step and aerator
trajectory methods of the same class as the USBR programs they mirror. Their
validity bounds are inherited from that class and are stated here explicitly:

1. **Hydrostatic pressure assumption.** The WS77 profile engine computes
   standard-step water-surface profiles with the curvature corrections of
   EM-42; it assumes hydrostatic pressure distributions across the section and
   does **not** resolve vertical accelerations or cross-wave/shock-wave
   patterns on steep chutes or in bends. Where EM-42 itself applies
   streamline-curvature corrections (concave/convex vertical curves), SWB
   follows the monograph's treatment — the same treatment whose post-1990
   revision is documented in `POST1990_DELTA.md` (row 11). Boundary-layer
   cavitation risk screening on curves is therefore a **screening-level**
   result, to be confirmed with physical-model or CFD studies for final design.
2. **1-D cross-section average.** All velocities/depths are section averages;
   local effects (piers, contractions, wall effects) enter only through the
   EM-42 section shapes (circular, composite, rectangular, trapezoidal) and
   not as separate flow features.
3. **Aerator trajectory.** The TRAJ engine implements the EM-42 Appendix D
   Glazov parametric nappe with the turbulence-dispersion tilt; it assumes
   well-ventilated cavity flow, does not model nappe vibration or partial
   aeration transients, and caps the vent solution at the documented limits
   (sonic vent velocity, pressure-drop fraction).
4. **Air-demand relations.** Air entrainment is the EM-42 cavity-opening /
   vent-hydraulics chain (Eq. 5.5 + Bernoulli cavity term) — empirical
   relations whose calibration is documented in the monograph, not new
   physics.
5. **What SWB is not.** Not a 2-D/3-D solver, not a physical-model substitute,
   and not a replacement for the USBR's current tool SpillwayPro where the
   agency's corrected equations are required (see `POST1990_DELTA.md`).

## 2. Verification design — the honest description (Reviewer 3-4, R1-1/2)

**The oracle structure, stated exactly.** The verification anchors are:

- **A1 — archived 1990 reference output** (GLENOUT for WS77; EM-42 p. 127
  printed tables for TRAJ Glen Canyon);
- **A2 — the original April-1990 binaries** bundled unmodified
  (`em_py/sample_data/`), executed under DOS emulation to produce the Blue
  Mesa trajectory table and the CKDATA/prompt-protocol behaviours.

A1 and A2 are **one lineage in two renderings** (typeset by USBR editors vs
executed by the compiled program): they are correlated by construction, and
SWB does **not** claim them as independent oracles. Matching both is a
consistency requirement (a transcription-error detector), not an independent
validation. The genuinely independent legs are:

- **L1 — closed-form internal checks:** the Glazov equations are linear with
  constant coefficients; the engine's closed-form solution is verified against
  RK4 integration to ≤ 1e-6 m (regression test), an implementation-level check
  independent of any USBR artifact.
- **L2 — published laboratory/field data:** EM-42's chapters compile
  laboratory measurements (air entrainment, boundary-layer growth) and case
  histories; the damage-index coefficients (Table 7.1) derive from Reclamation
  operating records. These anchor the physics independently of the programs.
- **L3 — cross-runs against the USBR's current tool:** SpillwayPro's published
  example applications (HL-2019-03, incl. the Glen Canyon appendix cases) are
  the natural modern cross-check; the *expected* outcome is agreement on
  corrected-physics quantities and **documented divergence on the three
  1990-bug behaviours** listed in `POST1990_DELTA.md` — divergence that is
  itself evidence of 1990 fidelity. (Planned for the next validation cycle;
  requires running the Excel tool on the shared cases.)

**Execution isolation (Reviewer 1-2, answered explicitly).** The automated
CI pipeline (`.github/workflows/build.yml`) does **not** execute the legacy
DOS binaries: CI runs the Python regression suites (frozen-oracle tests
against archived reference data A1 + internal check L1) headless on Linux.
Live execution of A2 (the binaries) is restricted to hosts with a DOS
emulator (author's Windows machine); the archived outputs of those runs are
deposited in the repository, which is what makes CI reproducible without
emulation. A standardized container (Docker/OCI) running DOSBox-x is the
planned upgrade path; until then the restriction is stated rather than
hidden. (From v1.2.1, the two engine regression suites `test_ws77_v11.py` and
`test_traj_v12.py` run in CI — previously the README claimed this and the
workflow did not do it.)

## 3. Terminology defined at first use (Reviewer 3-3, 13, 14)

- **Damage cross-recomputation** — the bidirectional bridge operation in
  which one engine's cavitation results are recomputed in the other engine's
  formalism: EM-Py's (σ, V, y) is re-evaluated through Cavicuspill's
  cavitation-number form (σ_flow, σ_uniform, damage potential), and
  Cavicuspill's damage-rate results are converted into EM-Py chamfer
  recommendations (implemented and tested in `bridge_hooks.py`:
  `em_damage_to_cav_recompute`, `cav_damage_to_chamfer_recommendations`).
- **Coefficient path** — the chain of empirical coefficients that carries one
  printed quantity back to its source equations; "rebuilt from Appendix D
  fragments" means: reconstructed from the equation fragments and worked
  examples of EM-42 Appendix D rather than closed against a second published
  source.
- **Appendix fragments** — the equation fragments, worked examples and
  prompt-protocol traces of EM-42 Appendix D ("Aerator Trajectory Program",
  pp. 125–129) used as decoding sources where the monograph text alone is
  incomplete.

## 4. The §4.5 "small discovery" resolved (Reviewer 3-12)

The sentence "Blue Mesa closes the matrix — and adds a small discovery"
left the discovery unnamed. The discovery is: **the Blue Mesa trajectory is
reproduced to 0.02 m while the vent pressure drop deviates (engine 0.00796
vs printed .006), and the deviation isolates exactly the term whose
coefficient path is not closed against an independent source — a localized
deviation in the reconstructed vent-pressure (cavitation) term, with the
original program's documented legacy PF/BV pressure factors excluded as
explanations both numerically and structurally by the executed closure test
(2026-11-23, six shadow runs R1–R6)** (see `POST1990_DELTA.md` rows 2–3 and
`closure_test/CLOSURE_TEST_PLAN.md` §4). State it in one sentence at the
point where the tease appears, or delete the tease.

## 5. On "open-source ≠ superiority" (Reviewer 4-10)

Accepted as stated: openness, cross-platform packaging and CI are software-
engineering virtues, not hydraulic-accuracy evidence. SWB's accuracy claims
rest exclusively on the verification design of §2; openness is offered as
inspectability (every quantitative statement traces to a file), not as
superiority. The comparison text against SpillwayPro and CFD presents them as
complements with different trade-offs, per the revision of the scope claim
(see `paper_patches/PATCHES.md`, patch P3).
