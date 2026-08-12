"""Sankey diagrams for matplotlib, as vector output.

    from sankey_mpl import render_sankey, save

    nodes = {"a": {"label": "Start", "color": "#5BB89F"},
             "b": {"label": "End", "color": "#6AA6F0"}}
    links = [{"from": "a", "to": "b", "flow": 100}]

    result = render_sankey(nodes, links)
    save(result, "diagram.svg")

The layout is a port of the JavaScript library ``chartjs-chart-sankey``, so
diagrams match what that library produces given the same input, apart from a
handful of documented differences listed in ``docs/usage.md``. See ``NOTICE`` for
the upstream copyright.
"""

from __future__ import annotations

from .config import DEFAULT_CONFIG
from .export import save
from .geometry import Frame
from .layout import Link, Node, SankeyLayout, compute_layout
from .render import (
    SankeyDrawing,
    SankeyFigure,
    build_frame,
    draw_sankey,
    render_sankey,
    text_width,
)

__all__ = [
    "DEFAULT_CONFIG",
    "Frame",
    "Link",
    "Node",
    "SankeyDrawing",
    "SankeyFigure",
    "SankeyLayout",
    "UPSTREAM_VERSION",
    "__version__",
    "build_frame",
    "compute_layout",
    "draw_sankey",
    "render_sankey",
    "save",
    "text_width",
]

__version__ = "0.1.0"

#: The ``chartjs-chart-sankey`` release this layout reproduces. Upstream changing
#: its algorithm would change what "matching" means, so the target is pinned.
UPSTREAM_VERSION = "0.15.0"
