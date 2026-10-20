"""Stable ``swb.bridge_hooks`` import path.

Re-exports the cross-bridge hooks (Cavicuspill <-> EM-Py domain
translations) from the canonical top-level module ``bridge_hooks.py``.
"""
from bridge_hooks import (  # noqa: F401
    ChamferRecommendation,
    cav_damage_to_chamfer_recommendations,
    em_damage_to_cav_recompute,
    em_geometry_to_cav_wes,
    find_aerator_station,
)

__all__ = [
    "ChamferRecommendation",
    "cav_damage_to_chamfer_recommendations",
    "em_damage_to_cav_recompute",
    "em_geometry_to_cav_wes",
    "find_aerator_station",
]
