# Spillway Workbench (SWB)

[![CI](https://github.com/darwishdasty-oss/spillway-workbench/actions/workflows/build.yml/badge.svg)](https://github.com/darwishdasty-oss/spillway-workbench/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.XXXXXXX-blue.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)

**Spillway Workbench (SWB)** is a unified, cross-platform engineering workbench
that merges two hydraulic programs into one Python 3 / PySide6 application:

| Sub-tool | Origin | Role |
|---|---|---|
| **Cavicuspill** | Abbas A. Hebah, 2004–2006 (VB6; M.Sc. thesis, Univ. of Sana'a) | Spillway **design**: flood routing → spillway dimensions → WES overflow profile → cavitation screening |
| **EM-Py** | Port of the USBR "Cavitation Programs" by Henry T. Falvey (1987, rev. 1990) | Cavitation **analysis**: water-surface profile, cavitation index, damage index, aerator trajectory, equal-σ design |

Both sub-tools share one MDI shell, one application state (`app_state.py`),
a reports menu, a CLI, and a PyInstaller-built single-file executable.

## Lineage

```
USBR Cavitation Programs (Falvey, FORTRAN 77, 1987/1990)
        │                                │
        ▼                                ▼
   EM-Py (2026) ◄──── bridge ────►  Cavicuspill (VB6, 2004-2006)
   cavitation analysis              spillway design
        └────────────►  SWB (Python, 2026)  ◄────────────┘
              unified workbench: design ↔ analysis
```

The **bridge** (`bridge_hooks.py`) implements domain-specific translations in
both directions: geometry exchange, damage-index cross-recomputation,
chamfer-recommendation generation, and aerator placement.

## What is included (v1.2.0)

| Component | Status |
|---|---|
| `cavicuspill/` — design tools (routing, WES profile, cavitation No., air entrainment, damage) | Ported |
| `em_py/` — EM-DINDX, CONVT, CKDATA, CONSTP | Fully ported & tested |
| `em_py/em_ws77.py` — water-surface profile | **Validated (v1.1)** — 27/27 stations inside the acceptance gate vs GLENOUT |
| `em_py/em_traj.py` — aerator trajectory | **Validated (v1.2)** — Glen Canyon 33/33 printed points; Blue Mesa 65/65 points within 0.02 m |
| `em_py/em_ecavno.py` | Framework stub |
| `swb/` — stable import package for the unified state and UI | Included |
| `canals/` — open-channel design suite | **Planned** |

### Honest status of the EM-Py ports

The data-file parsers (GLENIN/GLENOUT/GLENECN/ECNDAT/GLENHY/SPWY/HYDROL),
the unit converter, the data validator, the damage-index program (Falvey 1990
Table 7.1 coefficients), and the controlled-pressure distributions are faithful
ports verified by the test suite. The water-surface-profile engine **WS77 (v1.1)**
is validated against the USBR reference output GLENOUT (27/27 stations within
the gate of velocity ±5% and depth ±5% or 0.05 m; worst velocity deviation
1.06%), and the aerator-trajectory engine **TRAJ (v1.2)** is validated against
the original April-1990 binaries (Glen Canyon: all 33 printed points against
EM-42 p. 127; Blue Mesa: all 65 interpolated points within 0.02 m — the first
numerical record of that table). ECAVNO remains an algorithm *framework stub*;
treat its numeric output as indicative. Regression gates: `test_ws77_v11.py`
and `test_traj_v12.py` at the repository root (both run in CI). The bundled
USBR sample data (Glen Canyon, Blue Mesa, Hoover) is unmodified reference
material.

## Quick start

### Run from source (Windows / Linux / macOS)

```bash
pip install -r requirements.txt
python ui/mdi_main.py
```

### Run the prebuilt Windows executable

Download `SpillwayWorkbench.exe` (~110 MB, standalone, Windows 10/11 x64)
from the [Releases](https://github.com/darwishdasty-oss/spillway-workbench/releases)
page or from the Zenodo archive cited below. No Python installation is needed.

### Build the executable yourself

```bash
# Windows
build_windows.bat          # or: pyinstaller --noconfirm --clean swb.spec
```

The GitHub Actions workflow builds the .exe on every push to `main` and
attaches it (with a SHA256 checksum) to every `v*` release automatically.

## Command line (EM-Py modules)

```bash
python -m em_py.em_cli ws77 --input em_py/sample_data/DATA/GLENIN --calibrate em_py/sample_data/DATA/GLENOUT --output results.csv
python -m em_py.em_cli ckdata --input em_py/sample_data/DATA/GLENIN
python -m em_py.em_cli convt --value 283.168 --from cms --to cfs
```

## Tests

```bash
python test_swb.py -v       # merged workbench: state bridge, MDI shell, forms
```

CI runs the test suite headless (Qt offscreen) on Linux before every build.

## Repository layout

```
├── app_state.py            Unified application state (the bridge data store)
├── bridge_hooks.py         Domain-specific Cavicuspill <-> EM-Py translations
├── ui/mdi_main.py          Unified MDI shell (PyInstaller entry point)
├── cavicuspill/            Design tools (port of the author's VB6 program)
├── em_py/                  USBR Cavitation Programs port + bundled sample data
├── swb/                    Stable swb.* import paths
├── swb.spec                PyInstaller spec (single-file exe)
└── test_swb.py             Test suite
```

## License

- All **new code** in this repository: [MIT](LICENSE) © 2026 Abbas A. Hebah.
- The bundled original USBR DOS programs and sample data files
  (`em_py/sample_data/*.EXE`, `*.COM`, `*.BAT`, `DATA/*`) are works of the
  U.S. Federal Government (Bureau of Reclamation) and are in the **public
  domain** under 17 U.S.C. § 105. See [NOTICE.md](NOTICE.md).

## Citation

If you use SWB in research, please cite it (see [CITATION.cff](CITATION.cff)):

> Hebah, A. A. (2026). *Spillway Workbench (SWB): cross-platform Python
> reimplementation of the USBR Cavitation Programs and companion tool to
> Cavicuspill* (Version 1.2.0). Zenodo. https://doi.org/10.5281/zenodo.22839979
> (concept DOI — always resolves to the latest release)

The companion deposit for the original VB6 program **Cavicuspill** is archived
separately on Zenodo: https://doi.org/10.5281/zenodo.22817892

## References

- Falvey, H. T. (1990). *Cavitation in Chutes and Spillways*. USBR Engineering
  Monograph No. 42.
- Falvey, H. T. (1987). *Cavitation of Bureau of Reclamation Spillways* (with
  the associated FORTRAN program distribution), USBR.
- Hebah, A. A. (2004). *M.Sc. thesis*, University of Sana'a (the original
  Cavicuspill program).

## Acknowledgments

This port was derived from the original DOS FORTRAN 77 source distribution
(included under `em_py/sample_data/`) and the published USBR monographs. All
numerical formulas follow the published references.
