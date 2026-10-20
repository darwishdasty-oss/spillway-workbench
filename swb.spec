# -*- mode: python ; coding: utf-8 -*-
"""
swb.spec - PyInstaller spec for Spillway Workbench (Cavicuspill + EM-Py).

Build:
    pyinstaller swb.spec

Produces a single-file binary at dist/SpillwayWorkbench (~110 MB).
"""
import sys
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
SPECPATH = os.getcwd()
PROJECT_ROOT = SPECPATH

# Hidden imports
hiddenimports = []
hiddenimports += collect_submodules('matplotlib.backends')
hiddenimports += [
    'PySide6.QtCore', 'PySide6.QtWidgets', 'PySide6.QtGui', 'PySide6.QtPrintSupport',
    'numpy', 'matplotlib',
    # Sub-packages
    'cavicuspill', 'cavicuspill.ui', 'cavicuspill.ui.forms',
    'cavicuspill.ui.forms.reservoir_properties', 'cavicuspill.ui.forms.spillway_data',
    'cavicuspill.ui.forms.inflow_data', 'cavicuspill.ui.forms.outflow',
    'cavicuspill.ui.forms.spillway_profile', 'cavicuspill.ui.forms.spillway_properties',
    'cavicuspill.ui.forms.cross_section', 'cavicuspill.ui.forms.surface_profile',
    'cavicuspill.ui.forms.cavitation_no', 'cavicuspill.ui.forms.cavitation_damage',
    'cavicuspill.ui.forms.air_entrainment', 'cavicuspill.ui.forms.group_e',
    'cavicuspill.ui.charts', 'cavicuspill.ui.charts.matplotlib_widget',
    'em_py', 'em_py.ui', 'em_py.ui.forms',
    'em_py.ui.forms.ws77_form', 'em_py.ui.forms.plot77_form', 'em_py.ui.forms.traj_form',
    'em_py.ui.forms.ecavno_form', 'em_py.ui.forms.constp_form', 'em_py.ui.forms.dindx_form',
    'em_py.ui.forms.convt_form', 'em_py.ui.forms.ckdata_form', 'em_py.ui.forms.about_form',
    'em_py.ui.forms.group_e', 'em_py.ui.charts', 'em_py.ui.charts.matplotlib_widget',
    'swb', 'swb.ui',
]

# Data files
datas = [
    (os.path.join(PROJECT_ROOT, 'cavicuspill/cavicuspill.png'),  'swb/cavicuspill'),
    (os.path.join(PROJECT_ROOT, 'cavicuspill/cavicuspill.ico'),  'swb/cavicuspill'),
    (os.path.join(PROJECT_ROOT, 'em_py/sample_data'),           'swb/em_py'),
]

a = Analysis(
    ['ui/mdi_main.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='SpillwayWorkbench',
    debug=False, strip=False, upx=False,
)
