"""
em_ckdata.py - Geometry data checker (CKDATA tool).

Ported from CKDATA.EXE (Bureau of Reclamation Cavitation Programs, June 1987).
Henry T. Falvey, USBR.

The original CKDATA.EXE did two things:
  1. Read a .INP / .SPWY file and check for the presence of the title card,
     the consistency of the NSTA count, and the EOF position.
  2. Optionally reformat the file to a standardized column layout.

This Python port does (1) — the data check — and prints a validation report.
(2) is a no-op in the modern port: we read the file with our parser, so
reformatting would just re-write the same fields in a more readable form.

Validation checks performed:
  - Title card is present (non-empty)
  - NSTA matches the number of station records actually read
  - Stations are in monotonically increasing STA order
  - No station has a negative invert elevation
  - Discharge Q > 0
  - Initial depth y0 > 0
  - Roughness k_s >= 0
  - At least one station has rad_curv != 0 (curvature definition present)
  - WSE / reservoir elevation are consistent with at least one invert
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
from em_data import GeometryFile


@dataclass
class CheckResult:
    """A single validation finding."""
    severity: str  # "ERROR", "WARN", "INFO"
    code: str      # short identifier
    message: str


@dataclass
class CKDATAResult:
    title: str
    filename: str
    checks: List[CheckResult] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        return any(c.severity == "ERROR" for c in self.checks)
    
    @property
    def has_warnings(self) -> bool:
        return any(c.severity == "WARN" for c in self.checks)
    
    def summary(self) -> str:
        n_err = sum(1 for c in self.checks if c.severity == "ERROR")
        n_warn = sum(1 for c in self.checks if c.severity == "WARN")
        n_info = sum(1 for c in self.checks if c.severity == "INFO")
        return f"{n_err} errors, {n_warn} warnings, {n_info} info"


def check_data(g: GeometryFile, filename: str = "") -> CKDATAResult:
    """Run all data checks on a GeometryFile and return the result."""
    res = CKDATAResult(title=g.title, filename=filename, checks=[])
    _add = lambda sev, code, msg: res.checks.append(CheckResult(sev, code, msg))
    
    # Title check
    if not g.title.strip():
        _add("ERROR", "NO_TITLE", "NO TITLE CARD EXISTS")
    else:
        _add("INFO", "TITLE_OK", f"Title: {g.title.strip()[:60]!r}")
    
    # NSTA check
    if g.nsta <= 0:
        _add("ERROR", "NSTA_LE_0", f"NSTA = {g.nsta}, must be > 0")
    elif g.nsta != len(g.stations):
        _add("ERROR", "NSTA_MISMATCH",
             f"EOF OCCURRED AT NUMBER OF STATIONS - declared NSTA = {g.nsta}, "
             f"records read = {len(g.stations)}")
    else:
        _add("INFO", "NSTA_OK", f"NSTA = {g.nsta}, all stations read")
    
    # Discharge
    if g.q <= 0:
        _add("ERROR", "Q_LE_0", f"Discharge Q = {g.q}, must be > 0")
    
    # Initial depth
    if g.y0 < 0:
        _add("ERROR", "Y0_LT_0", f"Initial depth y0 = {g.y0}, must be >= 0")
    
    # Roughness
    if g.k_s < 0:
        _add("WARN", "K_S_LT_0", f"Roughness k_s = {g.k_s}, expected >= 0")
    
    # Stations
    if g.stations:
        # Monotonic station order
        for i in range(1, len(g.stations)):
            if g.stations[i].sta <= g.stations[i-1].sta:
                _add("ERROR", "STA_NOT_MONOTONIC",
                     f"Station {i+1} STA = {g.stations[i].sta} <= "
                     f"previous = {g.stations[i-1].sta}; "
                     f"EOF OCCURRED AT STATION {g.stations[i].sta}")
                break
        else:
            _add("INFO", "STA_MONOTONIC",
                 f"Stations monotonic from {g.stations[0].sta} "
                 f"to {g.stations[-1].sta}")
        
        # Negative inverts
        neg_inv = [s for s in g.stations if s.invert < 0]
        if neg_inv:
            _add("WARN", "INVERT_NEG",
                 f"{len(neg_inv)} stations have negative invert elevation")
        
        # At least one curvature defined
        if not any(s.rad_curv != 0 for s in g.stations):
            _add("WARN", "NO_CURVATURE",
                 "No station has radius of curvature defined (rad_curv = 0 everywhere)")
    
    # WSE / reservoir consistency
    if g.wse_initial and g.stations:
        first_invert = g.stations[0].invert
        if g.wse_initial < first_invert:
            _add("WARN", "WSE_BELOW_INVERT",
                 f"Initial WSE {g.wse_initial} < first station invert {first_invert}")
    
    if not res.has_errors:
        _add("INFO", "FILE_READ_CORRECTLY", "FILE READ CORRECTLY")
    
    return res


def format_report(res: CKDATAResult) -> str:
    """Format a CKDATAResult as a printable text report."""
    lines = []
    lines.append("=" * 70)
    lines.append("  CKDATA - Geometry Data Check")
    lines.append("=" * 70)
    if res.filename:
        lines.append(f"  File:   {res.filename}")
    if res.title:
        lines.append(f"  Title:  {res.title.strip()}")
    lines.append(f"  Result: {res.summary()}")
    lines.append("=" * 70)
    for c in res.checks:
        sym = {"ERROR": "[X]", "WARN": "[!]", "INFO": "[i]"}.get(c.severity, "[ ]")
        lines.append(f"  {sym} {c.severity:5s} {c.code:20s} {c.message}")
    lines.append("=" * 70)
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from em_data import read_geometry_file
    if len(sys.argv) < 2:
        # Demo on bundled sample
        g = read_geometry_file("sample_data/DATA/GLENIN")
        res = check_data(g, filename="sample_data/DATA/GLENIN")
        print(format_report(res))
    else:
        g = read_geometry_file(sys.argv[1])
        res = check_data(g, filename=sys.argv[1])
        print(format_report(res))
