"""Stable ``swb.ui.mdi_main`` import path.

Re-exports the unified MDI main window from the canonical top-level
module ``ui/mdi_main.py`` (the PyInstaller entry point).
"""
from ui.mdi_main import (  # noqa: F401
    SpillwayWorkbenchMainWindow,
    main,
)

__all__ = ["SpillwayWorkbenchMainWindow", "main"]
