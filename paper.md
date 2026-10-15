---
# P4-M1 JOSS paper — prepared 2026-10-13.
# M2 finalization steps (before submission):
#   1. `date:` set to the v1.0.1 Zenodo deposit date.
#   2. `archive-doi:` either keep the concept DOI (always resolves to the
#      latest version) or swap to the new v1.0.1 version DOI minted by the
#      deposit (the swap command is provided in the M1 package instructions).
title: 'Spillway Workbench (SWB): cross-platform Python reimplementation of the USBR Cavitation Programs and companion tool to Cavicuspill'
tags:
  - cavitation
  - spillway
  - hydraulic structures
  - flood routing
  - dam safety
authors:
  - name: Abbas Ahmed Mohammed Hebah
    orcid: 0009-0000-5689-2157
    affiliation: 1
affiliations:
  - name: Iran University of Science and Technology
    index: 1
date: 13 October 2026
bibliography: paper.bib
repository-code: https://github.com/darwishdasty-oss/spillway-workbench
archive-doi: 10.5281/zenodo.22839979
---

# Summary

Spillway Workbench (SWB) is a free, open-source desktop workbench that unifies spillway design and cavitation analysis in a single Python 3 / PySide6 application. It merges two complementary tools: Cavicuspill, a spillway design program covering reservoir flood routing, Waterways Experiment Station (WES) standard overflow profiles, and cavitation screening; and EM-Py, a Python reimplementation of the U.S. Bureau of Reclamation (USBR) Cavitation Programs distributed with Falvey's cavitation monographs, covering the water-surface profile, cavitation index, damage index, aerator trajectory, and equal-cavitation-number design. The sub-tools share one MDI shell, a unified application state, a command-line interface, and bidirectional bridges that convert design geometry into analysis inputs and cavitation findings back into design recommendations. The original USBR programs, still distributed as DOS executables, are treated as re-derivation targets rather than black boxes: EM-Py reimplements their published algorithms in auditable Python, while the unmodified public-domain USBR executables and sample data (Glen Canyon, Blue Mesa, Hoover) travel alongside for verification. A documented quality cycle accompanies the code: a certification audit exposed a silent solver defect that froze the water-surface profile in 74 of 360 benchmark reaches; v1.0.1 repairs the bracketing at the true critical depth, polishes roots to machine precision, and converts unsolvable reaches into loud, flagged failures, with an analytic gate passing at 1.53e-16 absolute error. SWB is released under the MIT license.

# Statement of need

Cavitation damage remains one of the principal threats to the long-term integrity of high-velocity spillway structures: when local pressure along a chute boundary drops toward vapor pressure, collapsing vapor cavities can pit concrete and steel, a mechanism documented across decades of Bureau of Reclamation field experience [@falvey1990]. The classical screening workflow for this risk is computational rather than experimental. The engineer computes the water-surface profile along the spillway, evaluates the local cavitation index at each station, compares it against incipient cavitation numbers for the relevant surface classifications, and decides on mitigation such as profile smoothing or aeration. Designers of new spillways, reviewers assessing existing structures, and educators teaching hydraulic design all need this workflow in a form that is transparent, scriptable, and available on any modern platform.

The reference implementation of the workflow is the pair of USBR Cavitation Programs distributed with Falvey's work [@falvey1987; @falvey1990]: FORTRAN-era DOS executables accompanied by batch scripts and sample data files. These binaries run only in legacy environments, cannot be inspected or corrected at the algorithm level, and expose none of their internal state. Computational fluid dynamics complements this screening by resolving the full two-phase flow field, but it demands specialized expertise, licensing, and computation time that are difficult to justify for routine design iterations and first-pass screening. To our knowledge, no maintained, open-source, cross-platform reimplementation of the documented algorithms behind the USBR programs is currently available.

SWB closes this gap in three ways. First, it reimplements the published algorithms in Python, module by module — the data-file parsers, the unit converter, the data validator, the damage-index program, and the water-surface-profile solver — while the original executables and their sample data are redistributed unmodified as United States Government works in the public domain, so that every port can be checked against the artifact it reimplements. Second, it integrates design and analysis in one place: the Cavicuspill design modules and the EM-Py analysis modules share a unified application state and bidirectional bridges, so geometry defined once serves both chains, and damage findings flow back into design recommendations. Third, it is engineered for verification: the test suite runs headless in continuous integration, the build is reproducible from source, and releases carry recorded hashes. The software is a direct extension of the author's earlier Cavicuspill program, whose original Visual Basic 6 implementation is archived on Zenodo [@cavicuspill2026].

The v1.0.1 release demonstrates why this structure matters. A certification audit found that the water-surface-profile solver split its root brackets at a heuristic depth instead of the section's true critical depth and, on bracket failure, silently returned the upstream depth: the profile froze while appearing to succeed, affecting 74 of 360 synthetic reaches. The repair re-brackets root pairs at the true critical depth, polishes every accepted root to machine precision, and converts genuinely unsolvable reaches into loud, flagged failures. On the same 360-reach grid, v1.0.1 produces zero freezes and reduces residual magnitudes by many orders, with an analytic gate error of 1.53e-16 against a tolerance of 1e-12, and a module-hash proof confirming that 54 of 58 files remained byte-identical — the fix is surgically scoped. A companion manuscript under review develops a benchmarking protocol for cavitation-screening surrogates in which SWB serves as the reference implementation of the classical workflow [@hebah2026pinn]. SWB is intended for spillway designers, dam-safety reviewers, and hydraulic engineering educators who need auditable access to this classical screening workflow on modern platforms.

# References
<!-- citations are rendered automatically from paper.bib -->
