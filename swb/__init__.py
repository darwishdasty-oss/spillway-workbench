"""
Spillway Workbench (SWB)
========================

A merged tool combining:
  - **Cavicuspill**: spillway *design* (flood routing -> spillway dimensions
    given Q and damage criteria)
  - **EM-Py**: cavitation *analysis* (spillway dimensions -> water surface
    profile, cavitation index, damage rates)

Both are ports to Python 3 / PySide6:
  - Cavicuspill (Abbas A. Hebah, 2004-2006; VB6 -> Python 2024-2026)
  - EM-Py (Henry T. Falvey's "Cavitation Programs" 1987/1990, ported 2026)

The two share an MDI shell, an APP_STATE, a Reports menu, a CLI, and a
PyInstaller-built single-file binary.

Note
----
The canonical implementation modules currently live at the repository top
level (``app_state.py``, ``bridge_hooks.py``, ``ui/``) because the PyInstaller
spec (``swb.spec``) and the Windows build script reference them there.  This
package provides stable ``swb.*`` import paths that re-export them, so both
layouts work:

    from swb.app_state import APP_STATE
    from swb.ui.mdi_main import SpillwayWorkbenchMainWindow

is equivalent to:

    from app_state import APP_STATE
    from ui.mdi_main import SpillwayWorkbenchMainWindow
"""
__version__ = "1.0.0"

__author__ = "Abbas A. Hebah"
__license__ = "MIT"
