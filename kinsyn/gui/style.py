"""Shared styling helpers for pyqtgraph plots."""

import pyqtgraph as pg
from PySide6 import QtGui


def style_plot(plot_item, pt, title=None, labels=None):
    """Apply text size `pt` to a PlotItem's title, axis labels and ticks.
    `labels` maps axis name -> label text (None keeps the current text)."""
    font = QtGui.QFont()
    font.setPointSizeF(pt)
    for name in ("left", "bottom"):
        axis = plot_item.getAxis(name)
        axis.setStyle(tickFont=font)
        text = (labels or {}).get(name, axis.labelText)
        if text:
            # Passing a style replaces pyqtgraph's default one, so restate the colour.
            color = pg.mkColor(pg.getConfigOption("foreground")).name()
            axis.setLabel(text, **{"font-size": f"{pt}pt", "color": color})
    if title is not None:
        plot_item.setTitle(title, size=f"{pt + 1}pt")
