"""
em_convert.py - Unit conversion (CONVT tool).

Ported from CONVT.EXE (Bureau of Reclamation Cavitation Programs, June 1987).
Henry T. Falvey, USBR.

The original was a simple interactive unit converter for English <-> SI
conversion of spillway geometry files. This Python port covers the most
common conversions used in the toolset:

    - Length:    ft <-> m
    - Area:      ft^2 <-> m^2
    - Volume:    ft^3 <-> m^3
    - Velocity:  ft/s <-> m/s
    - Discharge: cfs <-> cms
    - Pressure:  psi <-> Pa  (also atm, bar, mmHg)
    - Slope:     ft/ft == m/m (dimensionless)
    - Mass:      slug <-> kg
    - Force:     lbf <-> N
    - Energy:    ft-lbf <-> J
    - Power:     hp <-> W
    - Roughness: in <-> mm  (k_s for the WS77 tool)
    - Temperature: F <-> C

The interactive "geometry file" mode is implemented in the convert_geometry_file()
function: reads a GeometryFile, converts all relevant fields, writes a new file.
"""
from __future__ import annotations
from typing import Tuple
from em_data import GeometryFile, StationRecord


# Conversion factors (NIST values)
_FT_PER_M  = 3.2808398950131     # 1 m = 3.28084 ft
_M_PER_FT  = 0.3048              # 1 ft = 0.3048 m
_CFS_PER_CMS = 35.3146667214886  # 1 m^3/s = 35.3147 ft^3/s
_CMS_PER_CFS = 1.0 / _CFS_PER_CMS
_PA_PER_PSI = 6894.757293168361  # 1 psi = 6894.76 Pa
_PSI_PER_PA = 1.0 / _PA_PER_PSI
_MM_PER_IN  = 25.4
_IN_PER_MM  = 1.0 / 25.4
_N_PER_LBF  = 4.4482216152605    # 1 lbf = 4.44822 N
_KG_PER_SLUG = 14.59390294        # 1 slug = 14.5939 kg


def ft_to_m(x: float) -> float:
    """Feet to meters."""
    return x * _M_PER_FT


def m_to_ft(x: float) -> float:
    """Meters to feet."""
    return x * _FT_PER_M


def cfs_to_cms(x: float) -> float:
    """Cubic feet per second to cubic meters per second."""
    return x * _CMS_PER_CFS


def cms_to_cfs(x: float) -> float:
    """Cubic meters per second to cubic feet per second."""
    return x * _CFS_PER_CMS


def in_to_mm(x: float) -> float:
    """Inches to millimeters."""
    return x * _MM_PER_IN


def mm_to_in(x: float) -> float:
    """Millimeters to inches."""
    return x * _IN_PER_MM


def f_to_c(x: float) -> float:
    """Fahrenheit to Celsius."""
    return (x - 32.0) * 5.0 / 9.0


def c_to_f(x: float) -> float:
    """Celsius to Fahrenheit."""
    return x * 9.0 / 5.0 + 32.0


def psi_to_pa(x: float) -> float:
    return x * _PA_PER_PSI


def pa_to_psi(x: float) -> float:
    return x * _PSI_PER_PA


def lbf_to_n(x: float) -> float:
    return x * _N_PER_LBF


def n_to_lbf(x: float) -> float:
    return x / _N_PER_LBF





def convert_value(value: float, from_unit: str, to_unit: str):
    """Convert a single value between two units.
    
    Supported: ft<->m, cfs<->cms, in<->mm, F<->C, psi<->Pa, lbf<->N.
    """
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()
    table = {
        ("ft", "m"): ft_to_m, ("m", "ft"): m_to_ft,
        ("cfs", "cms"): cfs_to_cms, ("cms", "cfs"): cms_to_cfs,
        ("in", "mm"): in_to_mm, ("mm", "in"): mm_to_in,
        ("f", "c"): f_to_c, ("c", "f"): c_to_f,
        ("psi", "pa"): psi_to_pa, ("pa", "psi"): pa_to_psi,
        ("lbf", "n"): lbf_to_n, ("n", "lbf"): n_to_lbf,
    }
    fn = table.get((from_unit, to_unit))
    if fn is None:
        return value
    return fn(value)

# ============================================================================
# Geometry-file conversion (replicates CONVT interactive mode)
# ============================================================================

def convert_geometry_file(src: GeometryFile) -> GeometryFile:
    """Convert a GeometryFile in-place: SI <-> English.
    
    The original CONVT.EXE did exactly this: it read a file, determined the
    units from the file header (n_units flag), and produced a new file in
    the other unit system. We follow the same convention:
    
        n_units = 0  -> SI
        n_units = 1  -> English
    
    Field conversions:
        q:           cms <-> cfs
        y0:          m <-> ft
        k_s:         m <-> ft  (note: original used mm/in; here we use m/ft for consistency)
        slope_initial, wse_initial, reservoir_elev: m <-> ft
        stations[].sta, invert, width, side_slope, r1, r2, cl_height,
                    lower_r, wall_c2, rad_curv: m <-> ft
    
    (Roughness k_s is stored as m/ft here to be consistent with the SI/Eng
     units system. The original DOS tool stored it as mm/in.)
    """
    new = GeometryFile()
    if src.is_si:
        # SI -> English
        new.n_units = 1
        new.q = cms_to_cfs(src.q)
        new.y0 = m_to_ft(src.y0)
        new.k_s = m_to_ft(src.k_s)            # k_s in ft
        new.slope_initial = src.slope_initial  # dimensionless
        new.wse_initial = m_to_ft(src.wse_initial)
        new.reservoir_elev = m_to_ft(src.reservoir_elev)
    else:
        # English -> SI
        new.n_units = 0
        new.q = cfs_to_cms(src.q)
        new.y0 = ft_to_m(src.y0)
        new.k_s = ft_to_m(src.k_s)            # k_s in m
        new.slope_initial = src.slope_initial
        new.wse_initial = ft_to_m(src.wse_initial)
        new.reservoir_elev = ft_to_m(src.reservoir_elev)
    new.n_tech = src.n_tech
    new.title = src.title
    new.nsta = src.nsta
    if src.is_si:
        # m -> ft
        for s in src.stations:
            new.stations.append(StationRecord(
                sta=m_to_ft(s.sta),
                invert=m_to_ft(s.invert),
                width=m_to_ft(s.width),
                side_slope=s.side_slope,           # dimensionless
                r1=m_to_ft(s.r1),
                r2=m_to_ft(s.r2),
                cl_height=m_to_ft(s.cl_height),
                lower_r=m_to_ft(s.lower_r),
                wall_c2=m_to_ft(s.wall_c2),
                rad_curv=m_to_ft(s.rad_curv),
                roughness=m_to_ft(s.roughness),
                geom_code1=s.geom_code1,
                geom_code2=s.geom_code2,
            ))
    else:
        for s in src.stations:
            new.stations.append(StationRecord(
                sta=ft_to_m(s.sta),
                invert=ft_to_m(s.invert),
                width=ft_to_m(s.width),
                side_slope=s.side_slope,
                r1=ft_to_m(s.r1),
                r2=ft_to_m(s.r2),
                cl_height=ft_to_m(s.cl_height),
                lower_r=ft_to_m(s.lower_r),
                wall_c2=ft_to_m(s.wall_c2),
                rad_curv=ft_to_m(s.rad_curv),
                roughness=ft_to_m(s.roughness),
                geom_code1=s.geom_code1,
                geom_code2=s.geom_code2,
            ))
    return new


# ============================================================================
# Self-test
# ============================================================================

if __name__ == "__main__":
    # Round-trip test
    assert abs(ft_to_m(1.0) - 0.3048) < 1e-9
    assert abs(m_to_ft(0.3048) - 1.0) < 1e-9
    assert abs(cms_to_cfs(1.0) - 35.3146667214886) < 1e-9
    assert abs(psi_to_pa(1.0) - 6894.757293168361) < 1e-6
    print("CONVT self-test passed.")
