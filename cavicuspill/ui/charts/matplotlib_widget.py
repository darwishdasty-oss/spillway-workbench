"""
ui/charts/matplotlib_widget.py - A reusable Qt widget that embeds a
matplotlib Figure, so the PySide6 forms can show MSChart-2.0-style
plots just like the original VB6.

Copyright (c) 2026 Abbas A. Hebah. MIT License.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6 import QtWidgets


class MplCanvas(FigureCanvasQTAgg):
    """A matplotlib FigureCanvas that drops into a Qt layout."""

    def __init__(self, width: float = 6.0, height: float = 4.0, dpi: int = 100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        super().__init__(self.fig)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.updateGeometry()
