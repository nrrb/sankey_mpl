"""Drawing: node rectangles, ribbons, labels.

Everything is a vector artist. Nothing here rasterises, so SVG and PDF output
stay fully scalable and selectable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib import font_manager
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path
from matplotlib.textpath import TextPath

from .config import merge_config
from .geometry import Frame, control_points, cubic_point, cubic_subsegment
from .layout import Node, compute_layout

__all__ = [
    "SankeyDrawing",
    "SankeyFigure",
    "build_frame",
    "draw_sankey",
    "render_sankey",
    "text_width",
]

_NODE_Z = 1
_RIBBON_Z = 2
_LABEL_Z = 3


class SankeyDrawing:
    """A drawn diagram: everything that was resolved in order to draw it.

    What :func:`draw_sankey` returns. It carries no figure, because a diagram
    drawn into someone else's axes does not own one.
    """

    __slots__ = ("layout", "frame", "config", "labels", "labels_dropped")

    def __init__(
        self,
        frame: Frame,
        config: Mapping[str, Any],
        labels: list[dict[str, Any]],
        labels_dropped: list[str],
    ) -> None:
        self.frame = frame
        self.layout = frame.layout
        self.config = config
        #: One entry per drawn label: key, side, x, y, text.
        self.labels = labels
        #: Keys whose labels were suppressed for being too short to read.
        self.labels_dropped = labels_dropped

    def as_dict(self) -> dict[str, Any]:
        """Resolved geometry as plain data. Useful for tests and for debugging."""
        data = self.frame.as_dict()
        data["labels"] = self.labels
        data["labels_dropped"] = self.labels_dropped
        return data


class SankeyFigure(SankeyDrawing):
    """A rendered diagram: the figure, plus everything that was resolved to draw it."""

    __slots__ = ("figure",)

    def __init__(
        self,
        figure: Figure,
        frame: Frame,
        config: Mapping[str, Any],
        labels: list[dict[str, Any]],
        labels_dropped: list[str],
    ) -> None:
        super().__init__(frame, config, labels, labels_dropped)
        self.figure = figure


# --------------------------------------------------------------------------- #
# Colour
# --------------------------------------------------------------------------- #


def parse_color(value: Any) -> tuple[float, float, float]:
    """Accept CSS ``rgb()``/``rgba()`` as well as anything matplotlib understands.

    Web palettes routinely arrive in functional notation, which matplotlib
    rejects. Any alpha component is discarded: opacity belongs to ``link_alpha``,
    not smuggled in through a colour string.
    """
    if isinstance(value, (tuple, list)):
        return (float(value[0]), float(value[1]), float(value[2]))
    text = str(value).strip()
    if text.lower().startswith(("rgb(", "rgba(")):
        body = text[text.index("(") + 1 : text.rindex(")")]
        parts = [part.strip() for part in body.replace("/", ",").split(",")]
        channels = [
            float(part[:-1]) / 100.0 * 255.0 if part.endswith("%") else float(part)
            for part in parts[:3]
        ]
        return (channels[0] / 255.0, channels[1] / 255.0, channels[2] / 255.0)
    red, green, blue = to_rgb(text)
    return (float(red), float(green), float(blue))


def _blend(
    rgb: np.ndarray, alpha: float, background: tuple[float, float, float]
) -> tuple[float, float, float]:
    mixed = np.asarray(rgb) * alpha + np.asarray(background) * (1.0 - alpha)
    return (float(mixed[0]), float(mixed[1]), float(mixed[2]))


# --------------------------------------------------------------------------- #
# Ribbons
# --------------------------------------------------------------------------- #


def _ribbon_patches(
    frame: Frame, index: int, color_from: Any, color_to: Any
) -> list[PathPatch]:
    """One ribbon, as a run of flat-filled slices approximating a gradient.

    A matplotlib patch cannot carry a gradient fill. The alternative — a clipped
    image per ribbon — would rasterise the ribbons in every backend, so a ribbon
    is instead cut into ``n_strips`` slices, each an exact piece of the same
    cubic curve, each filled with the colour the gradient would have at its
    midpoint. The colour is sampled by horizontal position rather than by curve
    parameter, because the gradient this imitates runs left to right.

    Slices share edges. Each edge is antialiased on its own, so with real alpha
    the shared boundary shows as a faint hairline; ``link_flatten_alpha`` blends
    the colours against the background up front so the fills are opaque and the
    hairlines vanish, at the cost of ribbons no longer blending where they cross.
    """
    config = frame.config
    shape = frame.link_shape(index)
    x, x2 = shape["x"], shape["x2"]
    y, y2, height = shape["y"], shape["y2"], shape["height"]
    cp1, cp2 = control_points(x, y, x2, y2, config["control_point_split"])
    upper = np.array([(x, y), cp1, cp2, (x2, y2)], dtype=float)
    downward = np.array([0.0, height])

    flatten = bool(config["link_flatten_alpha"])
    alpha = float(config["link_alpha"])
    if flatten and config["background_color"] is None:
        raise ValueError(
            "link_flatten_alpha needs an opaque background_color to blend against"
        )
    background = (
        parse_color(config["background_color"])
        if config["background_color"]
        else (0.0, 0.0, 0.0)
    )
    rgb_from = np.asarray(parse_color(color_from))
    rgb_to = np.asarray(parse_color(color_to))
    slices = 1 if color_from == color_to else max(1, int(config["n_strips"]))
    span = x2 - x

    patches: list[PathPatch] = []
    for step in range(slices):
        t0, t1 = step / slices, (step + 1) / slices
        segment = cubic_subsegment(upper, t0, t1)
        mid_x = float(cubic_point(upper, (t0 + t1) / 2.0)[0])
        ratio = 0.0 if span == 0 else min(1.0, max(0.0, (mid_x - x) / span))
        rgb = rgb_from + (rgb_to - rgb_from) * ratio

        vertices = [
            tuple(segment[0]),
            tuple(segment[1]),
            tuple(segment[2]),
            tuple(segment[3]),
            tuple(segment[3] + downward),
            tuple(segment[2] + downward),
            tuple(segment[1] + downward),
            tuple(segment[0] + downward),
            tuple(segment[0]),
        ]
        codes = [
            Path.MOVETO,
            Path.CURVE4,
            Path.CURVE4,
            Path.CURVE4,
            Path.LINETO,
            Path.CURVE4,
            Path.CURVE4,
            Path.CURVE4,
            Path.CLOSEPOLY,
        ]
        patch = PathPatch(
            Path(vertices, codes),
            facecolor=(
                _blend(rgb, alpha, background)
                if flatten
                else (float(rgb[0]), float(rgb[1]), float(rgb[2]))
            ),
            alpha=None if flatten else alpha,
            edgecolor="none",
            linewidth=float(config["link_stroke_width_px"]),
            antialiased=True,
            zorder=_RIBBON_Z,
        )
        patch.set_rasterized(False)
        patch.set_clip_on(False)
        patches.append(patch)
    return patches


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #


def _font_properties(config: Mapping[str, Any]) -> FontProperties:
    return FontProperties(
        family=config["label_font_family"], size=float(config["label_font_size_px"])
    )


def text_width(text: str, config: Mapping[str, Any] | None = None) -> float:
    """Width of ``text`` in pixels, in the configured font.

    Measures the inked outline, which runs a hair narrower than the true advance
    width. That is the conservative direction for the gutter check: it will not
    claim a label fits when it does not by more than a fraction of a pixel.
    """
    merged = merge_config(config)
    if not text:
        return 0.0
    path = TextPath(
        (0.0, 0.0),
        text,
        size=float(merged["label_font_size_px"]),
        prop=_font_properties(merged),
    )
    return float(path.get_extents().width)


def _label_side(frame: Frame, node: Node) -> str:
    mode = frame.config["label_side_mode"]
    if mode == "left":
        return "left"
    if mode == "outside":
        # Point away from the middle of the plot: labels in the left half go
        # right, labels in the right half go left. Needs no gutter, but interior
        # labels then sit on top of the ribbons.
        midpoint = (frame.pad_left + (frame.width - frame.pad_right)) / 2.0
        return "right" if frame.x_pixel(node.column) < midpoint else "left"
    raise ValueError(f"label_side_mode must be 'left' or 'outside', not {mode!r}")


def _separate(centres: Sequence[float], min_gap: float) -> list[float]:
    """Push apart neighbours closer than ``min_gap``, moving both off their midpoint.

    Order-preserving, so labels never swap places, and iterated because moving one
    pair apart can close another.
    """
    result = list(centres)
    for _ in range(200):
        moved = False
        for i in range(1, len(result)):
            gap = result[i] - result[i - 1]
            if gap < min_gap:
                shift = (min_gap - gap) / 2.0
                result[i - 1] -= shift
                result[i] += shift
                moved = True
        if not moved:
            break
    return result


def _check_gutter(frame: Frame) -> float:
    """Refuse a gutter too narrow for the labels that have to fit in it."""
    config = frame.config
    if config["label_side_mode"] != "left":
        return 0.0
    offset = float(config["label_border_width_px"]) + float(config["label_padding_px"])
    widest, culprit = 0.0, ""
    for node in frame.layout.nodes.values():
        if node.column != 0:
            continue
        if frame.node_rect(node)[3] < float(config["min_label_height_px"]):
            continue
        label = node.label if node.label is not None else node.key
        width = text_width(label, config)
        if width > widest:
            widest, culprit = width, label
    if widest and widest + offset > frame.pad_left:
        raise ValueError(
            f"label_gutter_px={frame.pad_left:g} is too narrow: the widest label in "
            f"the first column, {culprit!r}, measures {widest:.1f}px and needs "
            f"{widest + offset:.1f}px including its {offset:g}px offset"
        )
    return widest


def _draw_labels(ax, frame: Frame) -> tuple[list[dict[str, Any]], list[str]]:
    config = frame.config
    offset = float(config["label_border_width_px"]) + float(config["label_padding_px"])
    color = parse_color(config["label_color"])
    font = _font_properties(config)

    columns: dict[int, list[tuple[Node, float, float, float]]] = {}
    dropped: list[str] = []
    for node in frame.layout.nodes.values():
        rect_x, rect_y, width, height = frame.node_rect(node)
        if height < float(config["min_label_height_px"]):
            dropped.append(node.key)
            continue
        columns.setdefault(node.column, []).append((node, rect_x, rect_y, height))

    placed: list[dict[str, Any]] = []
    for column in sorted(columns):
        members = sorted(columns[column], key=lambda item: item[2])
        centres = [rect_y + height / 2.0 for _, _, rect_y, height in members]
        if config["label_collision_separation"]:
            centres = _separate(centres, float(config["label_line_height_px"]))
        for (node, rect_x, _, _), centre in zip(members, centres, strict=True):
            side = _label_side(frame, node)
            text = node.label if node.label is not None else node.key
            if side == "right":
                text_x, align = rect_x + float(config["node_width_px"]) + offset, "left"
            else:
                text_x, align = rect_x - offset, "right"
            ax.text(
                text_x,
                centre,
                text,
                ha=align,
                # Canvas-style vertical centring is on the font's em box, not on
                # the inked bounding box. "center" would drift upward for text
                # without descenders; "center_baseline" uses font metrics.
                va="center_baseline",
                color=color,
                fontproperties=font,
                clip_on=False,
                zorder=_LABEL_Z,
            )
            placed.append(
                {"key": node.key, "side": side, "x": text_x, "y": centre, "text": text}
            )
    return placed, dropped


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


def build_frame(
    nodes: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> Frame:
    """Resolve everything needed to draw, without drawing or making a figure.

    Registers any ``font_paths``, computes the layout, builds the pixel frame and
    checks the label gutter. Call it when you need the diagram's final pixel size
    before committing to a place to put it: ``label_gutter_px`` and
    ``preserve_column_pitch`` both feed into ``frame.width``, so the width that
    comes out is not necessarily the ``width_px`` that went in.

    The returned frame carries the merged config as ``frame.config``.
    """
    merged = merge_config(config)
    # Before any text is measured: an unregistered family falls back silently, and
    # the gutter check and the label collision pass both measure text, so a late
    # registration would change the layout and not just the appearance.
    for path in merged["font_paths"]:
        font_manager.fontManager.addfont(path)

    frame_height = (
        float(merged["height_px"])
        - float(merged["pad_top"])
        - float(merged["pad_bottom"])
    )
    layout = compute_layout(
        nodes,
        links,
        gap_px=float(merged["node_gap_px"]),
        plot_height=frame_height,
        size_mode=merged["node_size_mode"],
        align_sinks_right=bool(merged["align_sinks_right"]),
    )
    frame = Frame(layout, merged)
    _check_gutter(frame)
    return frame


def _draw_into(ax, frame: Frame) -> tuple[list[dict[str, Any]], list[str]]:
    """Add the artists for ``frame`` to ``ax``, and report the labels placed.

    Assumes ``ax`` is already in the pixel coordinate system the frame describes.
    Takes no ``links`` argument: the layout retains them, in input order, which is
    the order the ribbons have to be drawn in for overlaps to stack as upstream's.
    """
    config = frame.config

    # Nodes first, then ribbons in input order, then labels on top.
    for node in frame.layout.nodes.values():
        rect_x, rect_y, width, height = frame.node_rect(node)
        rect = Rectangle(
            (rect_x, rect_y),
            width,
            height,
            facecolor=parse_color(node.color) if node.color else (0.0, 0.0, 0.0),
            edgecolor=(
                parse_color(config["node_edge_color"])
                if config["node_edge_color"]
                else "none"
            ),
            linewidth=float(config["node_edge_width_px"]),
            antialiased=True,
            clip_on=False,
            zorder=_NODE_Z,
        )
        rect.set_rasterized(False)
        ax.add_patch(rect)

    for index, link in enumerate(frame.layout.links):
        source = frame.layout.nodes[link["from"]]
        target = frame.layout.nodes[link["to"]]
        for patch in _ribbon_patches(
            frame,
            index,
            source.color if source.color else "#000000",
            target.color if target.color else "#000000",
        ):
            ax.add_patch(patch)

    return _draw_labels(ax, frame)


def draw_sankey(
    ax,
    nodes: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> SankeyDrawing:
    """Draw a sankey diagram into an existing axes.

    For embedding a diagram in a larger figure — a report page, a dashboard, a
    multi-panel comparison. :func:`render_sankey` is the same drawing with a
    figure of its own.

    ``nodes``, ``links`` and ``config`` mean exactly what they mean for
    :func:`render_sankey`.

    Sets the axes limits itself, to ``xlim (0, frame.width)`` and ``ylim
    (frame.height, 0)``, and turns the axes off. That is not a convenience: those
    limits *are* the one-unit-is-one-pixel contract, and getting them wrong
    rescales the diagram silently rather than failing, so it should not be
    possible to get wrong.

    It does **not** set the axes facecolor, because an embedded diagram sits on a
    surface its host has already painted. In this path ``background_color``
    therefore only does its other job, which is telling
    ``link_flatten_alpha=True`` what to pre-blend the ribbons against — so it
    still has to be set, and set to the colour actually behind the diagram, or the
    ribbons come out tinted for a surface that isn't there.

    Two configuration notes that only matter when embedding:

    * Set ``preserve_column_pitch=False`` and ``width_px`` to the width of the box
      you are drawing into. The default widens the diagram to offset the label
      gutter — a 900px request becomes 1097px with the default 200px gutter —
      which would overflow the space you allotted.
    * Size the axes from ``build_frame()`` first if you need the width to be
      exact, or assert ``frame.width`` against your box afterwards. This function
      returns the frame on ``.frame`` for that.
    """
    frame = build_frame(nodes, links, config)
    ax.set_xlim(0.0, frame.width)
    ax.set_ylim(frame.height, 0.0)  # y downward
    ax.set_axis_off()
    labels, dropped = _draw_into(ax, frame)
    return SankeyDrawing(frame, frame.config, labels, dropped)


def render_sankey(
    nodes: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> SankeyFigure:
    """Draw a sankey diagram.

    Parameters
    ----------
    nodes
        ``{key: {"label": str, "color": str}}``. Both entries are optional: the
        key is used when no label is given, and an uncoloured node is drawn black.
        Keys not appearing in ``links`` are ignored. Pass an ordered mapping —
        any ``dict`` — because iteration order breaks ties between equal
        positions.
    links
        ``[{"from": key, "to": key, "flow": number}, ...]``. The order matters:
        it is the final tie-break in vertical placement, so the same links in a
        different order can produce a different diagram.
    config
        Overrides for :data:`sankey_mpl.DEFAULT_CONFIG`. Unknown keys raise.

    Returns
    -------
    SankeyFigure
        Holds ``.figure`` for saving or embedding, and the resolved layout.
    """
    frame = build_frame(nodes, links, config)
    merged = frame.config

    dpi = 72.0 * float(merged["device_pixel_ratio"])
    background = (
        "none"
        if merged["background_color"] is None
        else parse_color(merged["background_color"])
    )
    figure = Figure(
        figsize=(frame.width / 72.0, frame.height / 72.0),
        dpi=dpi,
        facecolor=background,
    )
    ax = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(0.0, frame.width)
    ax.set_ylim(frame.height, 0.0)  # y downward
    # Unlike draw_sankey, this figure owns its background, so it paints it.
    ax.set_facecolor(background)
    ax.set_axis_off()

    placed, dropped = _draw_into(ax, frame)
    return SankeyFigure(figure, frame, merged, placed, dropped)
