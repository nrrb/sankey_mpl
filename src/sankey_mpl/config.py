"""Configuration defaults and validation.

Every tunable lives here as a plain dict entry so it can be overridden without
touching code. ``render_sankey`` rejects unknown keys rather than ignoring them,
which turns a typo into an error instead of a silently unchanged diagram.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

__all__ = ["DEFAULT_CONFIG", "merge_config"]


DEFAULT_CONFIG: dict[str, Any] = {
    # ---- canvas ----------------------------------------------------------- #
    # Figure size in CSS-style pixels. One pixel here is one point in the output,
    # so an SVG or PDF lands at exactly these dimensions.
    "width_px": 900,
    "height_px": 360,
    # Raster export scale: dpi = 72 * this. 1 gives a 1:1 PNG, 3 a 3x PNG. It
    # never affects layout — only how many device pixels the output has.
    "device_pixel_ratio": 3,
    # Space between the plot area and the figure edge. `pad_left` comes from
    # `label_gutter_px`; `pad_right` defaults to node_width_px + 3, which is the
    # minimum that fits the last column's node rectangles.
    "pad_top": 3,
    "pad_bottom": 3,
    "pad_right": None,
    # Room reserved on the left for labels. Only column 0's labels can land here,
    # and under the default `label_side_mode` they point right instead, so the
    # default is just a hairline margin. Raise it when switching to "left" mode,
    # which needs the whole widest first-column label to fit: `text_width()` sizes
    # it from real data. The two keys are coupled; changing one alone looks wrong.
    "label_gutter_px": 3,
    # A gutter eats into the plot area, which shortens every ribbon. True widens
    # the figure to keep the column spacing instead; False accepts narrower
    # columns. Either way the choice is reported back on the result.
    "preserve_column_pitch": True,
    # None exports with a transparent background so the diagram composites onto
    # whatever page it lands on. Set a colour to bake one in.
    "background_color": None,
    # ---- nodes ------------------------------------------------------------ #
    "node_width_px": 10,
    # "max" sizes a node by the larger of its inflow and outflow, "min" by the
    # smaller. "min" can make a node shorter than its own links, which is
    # rejected rather than drawn with overlapping ribbons.
    "node_size_mode": "max",
    # Vertical gap between nodes in a column, in pixels, honoured exactly.
    "node_gap_px": 4.5,
    "node_edge_color": None,
    "node_edge_width_px": 0.0,
    # Push every node that has no outgoing links into the last column, so short
    # paths finish flush with long ones.
    "align_sinks_right": True,
    # ---- links ------------------------------------------------------------ #
    # Gap between a node's edge and the ribbons attached to it.
    "link_inset_px": 1.0,
    "link_alpha": 0.5,
    # Where the two Bezier control points sit along the horizontal span, as
    # fractions. Note they cross: the first is further along than the second,
    # which is what gives the ribbon its flat approach and steep middle.
    "control_point_split": (2.0 / 3.0, 1.0 / 3.0),
    # A ribbon is drawn as this many flat-filled slices to fake a gradient, since
    # a single patch cannot carry one. Below ~24 the banding becomes visible.
    "n_strips": 48,
    # Blend each slice against `background_color` up front instead of relying on
    # alpha. Removes the hairlines where slices meet, but ribbons then paint over
    # each other opaquely instead of blending. Needs an opaque background.
    "link_flatten_alpha": False,
    "link_stroke_width_px": 0.0,
    # ---- labels ----------------------------------------------------------- #
    "label_font_family": ["DejaVu Sans"],
    "label_font_size_px": 12,
    # Minimum vertical distance between two labels in the same column.
    "label_line_height_px": 14.4,
    "label_color": "#20282C",
    "label_padding_px": 4,
    "label_border_width_px": 1,
    # "outside" points labels away from the middle: columns in the left half of the
    # plot get their label on the right, columns in the right half on the left. This
    # mirrors the original library and is the default because it is what readers of
    # a sankey expect, and because it needs no gutter. The cost is that interior
    # labels sit on top of the ribbons leaving their own node.
    #
    # "left" puts every label to the left of its node instead, which keeps text off
    # the ribbons entirely but needs `label_gutter_px` widened to fit column 0's
    # labels, and refuses to draw if they do not fit.
    "label_side_mode": "outside",
    # Nodes shorter than this get no label, on the grounds that no label beats
    # two overlapping ones.
    "min_label_height_px": 8,
    # After dropping, nudge apart any labels still closer than
    # `label_line_height_px`.
    "label_collision_separation": True,
    # Font files to register with matplotlib before drawing, e.g. a bundled .ttf.
    "font_paths": [],
    # ---- export ----------------------------------------------------------- #
    # "none" keeps SVG text as text, which stays selectable but needs the font
    # available wherever the SVG is opened. "path" converts glyphs to outlines:
    # self-contained and pixel-identical anywhere, but no longer selectable.
    "svg_fonttype": "none",
    # Type 3 fonts (matplotlib's default 3) render fine but cannot be selected or
    # searched in a PDF. 42 embeds TrueType instead.
    "pdf_fonttype": 42,
    "ps_fonttype": 42,
    # Fixes the element ids matplotlib would otherwise derive from memory
    # addresses, so repeated renders of the same input produce the same bytes.
    "svg_hashsalt": "sankey_mpl",
}


def merge_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Overlay ``config`` on the defaults, rejecting unknown keys."""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if not config:
        return merged
    unknown = sorted(set(config) - set(merged))
    if unknown:
        raise ValueError(f"unknown config keys: {unknown}. Valid keys: {sorted(merged)}")
    merged.update(config)
    return merged
