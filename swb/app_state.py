"""Stable ``swb.app_state`` import path.

Re-exports the unified application state from the canonical top-level
module ``app_state.py`` (see ``swb/__init__.py`` for the layout note).
"""
from app_state import APP_STATE, SpillwayWorkbenchState  # noqa: F401

__all__ = [
    "APP_STATE",
    "SpillwayWorkbenchState",
]
