"""
ui/charts/matplotlib_widget.py - Reusable Qt + matplotlib widget.
"""
from __future__ import annotations
from PySide6 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class MplCanvas(FigureCanvasQTAgg):
    """A matplotlib FigureCanvas that drops into Qt layouts.
    
    Usage:
        canvas = MplCanvas(width=8, height=5, dpi=100)
        layout.addWidget(canvas)
        ax = canvas.fig.add_subplot(111)
        ax.plot(...)
        canvas.draw()
    """
    def __init__(self, width: float = 6.0, height: float = 4.0, dpi: int = 100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.set_tight_layout(True)
        super().__init__(self.fig)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
