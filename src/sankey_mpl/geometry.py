"""Flow units to pixels: scales, node rectangles, ribbon outlines.

The coordinate contract for the whole library is set here, and it is what keeps
the rest of the code free of unit conversions. The figure is sized so that

    one data unit  =  one point  =  one pixel

by making the figure ``width_px / 72`` inches wide and letting a single axes fill
it, with the y-axis inverted so y grows downward like a screen coordinate. The
consequences are worth stating because they remove a whole class of bug:

* ``fontsize=12`` means 12 pixels tall, at any dpi. No ``72 / dpi`` factor
  belongs anywhere in this library — if one seems necessary, the figure size has
  been tampered with.
* Line widths take pixel values directly.
* dpi becomes purely an export scale: 72 for a 1:1 raster, 216 for 3x. Vector
  formats measure in points, so they land at exactly ``width_px`` by
  ``height_px``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .layout import Node, SankeyLayout

__all__ = ["Frame", "control_points", "cubic_subsegment", "cubic_point"]


class Frame:
    """The pixel frame a layout is drawn into."""

    __slots__ = (
        "layout",
        "config",
        "width",
        "requested_width",
        "height",
        "pad_top",
        "pad_bottom",
        "pad_left",
        "pad_right",
        "plot_width",
        "plot_height",
        "px_per_unit",
        "column_pitch_preserved",
    )

    def __init__(self, layout: SankeyLayout, config: Mapping[str, Any]) -> None:
        self.layout = layout
        self.config = config

        node_width = float(config["node_width_px"])
        self.pad_top = float(config["pad_top"])
        self.pad_bottom = float(config["pad_bottom"])
        self.pad_left = float(config["label_gutter_px"])
        self.pad_right = float(
            node_width + 3 if config["pad_right"] is None else config["pad_right"]
        )
        # The last column's rectangles start at the plot area's right edge and
        # extend node_width beyond it, so the right padding has to cover them.
        if self.pad_right < node_width + 3:
            raise ValueError(
                f"pad_right must be at least node_width_px + 3 ({node_width + 3:g}) "
                f"to fit the last column's nodes; got {self.pad_right:g}"
            )

        self.requested_width = float(config["width_px"])
        self.column_pitch_preserved = bool(config["preserve_column_pitch"])
        # A left gutter narrows the plot area, which shortens every ribbon and
        # steepens its curve. Widening the figure by the extra gutter keeps the
        # column spacing the caller would have got without one.
        self.width = (
            self.requested_width + (self.pad_left - 3.0)
            if self.column_pitch_preserved
            else self.requested_width
        )
        self.height = float(config["height_px"])

        self.plot_width = self.width - self.pad_left - self.pad_right
        self.plot_height = self.height - self.pad_top - self.pad_bottom
        if self.plot_width <= 0 or self.plot_height <= 0:
            raise ValueError(
                "padding leaves no room to draw: plot area is "
                f"{self.plot_width:g} x {self.plot_height:g} px"
            )

        self.px_per_unit = self.plot_height / layout.total_height

    # -- scales ------------------------------------------------------------- #

    def x_pixel(self, column: float) -> float:
        return self.pad_left + (column / self.layout.max_column) * self.plot_width

    def y_pixel(self, units: float) -> float:
        return self.pad_top + (units / self.layout.total_height) * self.plot_height

    # -- artefact geometry -------------------------------------------------- #

    def node_rect(self, node: Node) -> tuple[float, float, float, float]:
        """``(x, y, width, height)`` in pixels, with y measured downward."""
        return (
            self.x_pixel(node.column),
            self.y_pixel(node.y),
            float(self.config["node_width_px"]),
            node.size * self.px_per_unit,
        )

    def link_shape(self, index: int) -> dict[str, float]:
        """One ribbon's endpoints and thickness, in pixels.

        Thickness comes from the source side only, and the ribbon's lower edge is
        its upper edge shifted straight down by that amount. Ribbons therefore do
        not taper, even where a node's inflow and outflow differ.
        """
        link = self.layout.links[index]
        source = self.layout.nodes[link["from"]]
        target = self.layout.nodes[link["to"]]
        inset = float(self.config["link_inset_px"])
        start_units = source.y + self.layout.link_offset(
            source, "outgoing", link["to"], index
        )
        end_units = target.y + self.layout.link_offset(
            target, "incoming", link["from"], index
        )
        return {
            "x": self.x_pixel(source.column)
            + float(self.config["node_width_px"])
            + inset,
            "x2": self.x_pixel(target.column) - inset,
            "y": self.y_pixel(start_units),
            "y2": self.y_pixel(end_units),
            "height": float(link["flow"]) * self.px_per_unit,
        }

    def as_dict(self) -> dict[str, Any]:
        """A JSON-friendly dump of everything resolved, for tests and debugging."""
        return {
            "width": self.width,
            "requested_width": self.requested_width,
            "height": self.height,
            "column_pitch_preserved": self.column_pitch_preserved,
            "padding": {
                "top": self.pad_top,
                "right": self.pad_right,
                "bottom": self.pad_bottom,
                "left": self.pad_left,
            },
            "plot_width": self.plot_width,
            "plot_height": self.plot_height,
            "max_column": self.layout.max_column,
            "total_height": self.layout.total_height,
            "total_height_unpadded": self.layout.total_height_unpadded,
            "gap_units": self.layout.gap_units,
            "gap_slots_at_max": self.layout.gap_slots_at_max,
            "rendered_gap_px": self.layout.gap_units * self.px_per_unit,
            "px_per_unit": self.px_per_unit,
            "nodes": {
                node.key: {
                    "column": node.column,
                    "y": node.y,
                    "y_unpadded": node.y_unpadded,
                    "gap_slots": node.gap_slots,
                    "size": node.size,
                    "rect": self.node_rect(node),
                }
                for node in self.layout.nodes.values()
            },
            "links": [
                {
                    "from": link["from"],
                    "to": link["to"],
                    "flow": link["flow"],
                    "offset": self.layout.link_offset(
                        self.layout.nodes[link["from"]], "outgoing", link["to"], index
                    ),
                    **self.link_shape(index),
                }
                for index, link in enumerate(self.layout.links)
            ],
        }


# --------------------------------------------------------------------------- #
# Cubic Bezier helpers
# --------------------------------------------------------------------------- #


def control_points(
    x: float, y: float, x2: float, y2: float, split: Sequence[float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    """The two control points for a ribbon's upper edge.

    They cross over: the point belonging to the start sits ``split[0]`` of the way
    along at the start's height, and the point belonging to the end sits
    ``split[1]`` of the way along at the end's height. With the default (2/3, 1/3)
    that is further along for the start than for the end, which is not the usual
    both-at-the-midpoint sankey curve. It produces a flatter approach at each end
    and a steeper middle, and it is the single most visible thing to get wrong.
    """
    span = x2 - x
    return (x + span * split[0], y), (x + span * split[1], y2)


def cubic_point(points: np.ndarray, t: float) -> np.ndarray:
    """Evaluate a cubic Bezier at ``t``."""
    u = 1.0 - t
    return (
        u**3 * points[0]
        + 3.0 * u**2 * t * points[1]
        + 3.0 * u * t**2 * points[2]
        + t**3 * points[3]
    )


def _split_right(points: np.ndarray, t: float) -> np.ndarray:
    """de Casteljau: the piece of the curve over ``[t, 1]``, as its own cubic."""
    p01 = points[0] + (points[1] - points[0]) * t
    p12 = points[1] + (points[2] - points[1]) * t
    p23 = points[2] + (points[3] - points[2]) * t
    p012 = p01 + (p12 - p01) * t
    p123 = p12 + (p23 - p12) * t
    return np.array([p012 + (p123 - p012) * t, p123, p23, points[3]])


def cubic_subsegment(points: np.ndarray, t0: float, t1: float) -> np.ndarray:
    """The piece of the curve over ``[t0, t1]``, exactly.

    Exact matters: the slices a ribbon is cut into for its gradient share edges
    with their neighbours, and a chord approximation would leave those edges off
    the true curve, visibly faceting the ribbon's outline.
    """
    if t1 < 1.0:
        # The left piece is the right piece of the reversed curve.
        points = _split_right(points[::-1], 1.0 - t1)[::-1]
        t0 = t0 / t1 if t1 else 0.0
    return _split_right(points, t0) if t0 > 0.0 else points
