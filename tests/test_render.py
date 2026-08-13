"""Drawing behaviour: vector output, label rules, figure dimensions."""

from __future__ import annotations

import hashlib

import pytest
from matplotlib.figure import Figure

from sankey_mpl import build_frame, draw_sankey, render_sankey, save, text_width


@pytest.fixture
def wide_enough(nodes) -> dict:
    """A gutter that fits the dataset's longest first-column label.

    Only `label_side_mode="left"` needs this, since the default points column 0's
    labels rightward into the plot instead. Tests that are not about labels still
    take it, because it costs nothing and keeps them insensitive to the default.

    Deliberately computed rather than hardcoded: a constant here would encode one
    dataset's longest label and fail on the next one, or on a font change.
    """
    longest = max(
        (spec.get("label", key) for key, spec in nodes.items() if key.startswith("src:")),
        key=len,
    )
    return {"label_gutter_px": text_width(longest) + 20}


def test_figure_dimensions_follow_the_pixel_contract(nodes, links, wide_enough):
    result = render_sankey(nodes, links, wide_enough)
    width, height = result.figure.get_size_inches()
    assert width * 72 == pytest.approx(result.frame.width)
    assert height * 72 == pytest.approx(360)


def test_device_pixel_ratio_only_changes_dpi(nodes, links, wide_enough):
    one = render_sankey(nodes, links, {**wide_enough, "device_pixel_ratio": 1})
    three = render_sankey(nodes, links, {**wide_enough, "device_pixel_ratio": 3})
    assert one.figure.dpi == 72
    assert three.figure.dpi == 216
    # Same layout, different raster scale.
    assert one.as_dict()["links"] == three.as_dict()["links"]


def test_gutter_widens_the_figure_by_default(nodes, links, wide_enough):
    preserved = render_sankey(nodes, links, wide_enough)
    compressed = render_sankey(
        nodes, links, {**wide_enough, "preserve_column_pitch": False}
    )
    assert preserved.frame.width > compressed.frame.width
    # Widening exists to keep the column spacing, so the plot area should match
    # what a 3px left padding would have given.
    assert preserved.frame.plot_width == pytest.approx(900 - 3 - 13)
    assert compressed.frame.plot_width < preserved.frame.plot_width


def test_thin_nodes_lose_their_labels(nodes, links, wide_enough):
    result = render_sankey(nodes, links, wide_enough)
    assert result.labels_dropped, "the example has nodes too thin to label"
    resolved = result.as_dict()["nodes"]
    for key in result.labels_dropped:
        assert resolved[key]["rect"][3] < 8
    for label in result.labels:
        assert resolved[label["key"]]["rect"][3] >= 8


def test_dropping_can_be_switched_off(nodes, links, wide_enough):
    kept = render_sankey(nodes, links, {**wide_enough, "min_label_height_px": 0})
    assert kept.labels_dropped == []
    assert len(kept.labels) == len(kept.layout.nodes)


def test_labels_point_outward_from_the_middle_by_default(nodes, links):
    """The default mirrors the reference: away from the middle of the plot.

    Asserts the *split*, not merely that both sides occur, because "both sides
    appear somewhere" would still pass if the sides were assigned per node instead
    of per column, which is the mistake that would look almost right.
    """
    result = render_sankey(nodes, links)

    by_column: dict[int, set[str]] = {}
    for label in result.labels:
        column = result.layout.nodes[label["key"]].column
        by_column.setdefault(column, set()).add(label["side"])

    for column, sides in by_column.items():
        assert len(sides) == 1, f"column {column} has labels on both sides: {sides}"

    # The outermost columns are the two the rule is unambiguous about: column 0 is
    # always in the left half and the last column always in the right half.
    assert by_column[min(by_column)] == {"right"}
    assert by_column[max(by_column)] == {"left"}

    # Right-pointing columns must all come before left-pointing ones; a single
    # switchover is what "outward from the middle" means.
    sides_in_order = [next(iter(by_column[c])) for c in sorted(by_column)]
    assert sides_in_order == sorted(sides_in_order, reverse=True), sides_in_order


def test_left_mode_puts_every_label_on_the_left(nodes, links, wide_enough):
    """The alternative, which needs the gutter that `wide_enough` supplies."""
    result = render_sankey(nodes, links, {**wide_enough, "label_side_mode": "left"})
    assert {label["side"] for label in result.labels} == {"left"}


# Comfortably above the natural label spacing of every dataset, so each one has
# collisions for separation to resolve. Raising the line height rather than
# shrinking the figure is deliberate: it manufactures crowding without touching
# geometry, so the test cannot start failing for the unrelated reason that a
# shorter figure tripped the gap or padding guard.
CROWDING_LINE_HEIGHT = 36.0


def test_collision_separation_enforces_the_line_height(nodes, links, wide_enough):
    config = {
        **wide_enough,
        "min_label_height_px": 0,
        "label_line_height_px": CROWDING_LINE_HEIGHT,
    }
    crowded = render_sankey(nodes, links, {**config, "label_collision_separation": False})
    spaced = render_sankey(nodes, links, {**config, "label_collision_separation": True})

    def smallest_gap(result):
        worst = float("inf")
        by_column: dict[int, list[float]] = {}
        for label in result.labels:
            column = result.layout.nodes[label["key"]].column
            by_column.setdefault(column, []).append(label["y"])
        for values in by_column.values():
            ordered = sorted(values)
            for a, b in zip(ordered, ordered[1:], strict=False):
                worst = min(worst, b - a)
        return worst

    assert smallest_gap(crowded) < CROWDING_LINE_HEIGHT
    assert smallest_gap(spaced) == pytest.approx(CROWDING_LINE_HEIGHT, abs=1e-6)


def test_separation_preserves_label_order(nodes, links, wide_enough):
    """Within a column. Separation is per-column, so it can and does reorder
    labels relative to labels in *other* columns — that is not a violation."""
    config = {
        **wide_enough,
        "min_label_height_px": 0,
        # Same crowding as the test above, so separation has real work to do here
        # rather than trivially preserving an order it never had to disturb.
        "label_line_height_px": CROWDING_LINE_HEIGHT,
    }
    before = render_sankey(nodes, links, {**config, "label_collision_separation": False})
    after = render_sankey(nodes, links, {**config, "label_collision_separation": True})

    def order_by_column(result):
        columns: dict[int, list[tuple[float, str]]] = {}
        for label in result.labels:
            column = result.layout.nodes[label["key"]].column
            columns.setdefault(column, []).append((label["y"], label["key"]))
        return {
            column: [key for _, key in sorted(entries)]
            for column, entries in columns.items()
        }

    assert order_by_column(before) == order_by_column(after)


def test_svg_contains_no_raster_images(nodes, links, wide_enough, tmp_path):
    result = render_sankey(nodes, links, wide_enough)
    path = tmp_path / "diagram.svg"
    save(result, str(path))
    body = path.read_text()
    assert "<image" not in body, "something rasterised"
    assert "data:image" not in body
    assert body.count("<path") > 100, "ribbons should be paths"


def test_svg_keeps_text_as_text_by_default(nodes, links, wide_enough, tmp_path):
    """Every label is a real SVG text element, so it stays selectable.

    Asserted as text elements rather than by grepping for ``font-family``, which is
    how current matplotlib happens to express the font and not how every supported
    version does. On matplotlib 3.7 the same diagram carries proper ``<text>``
    elements and no ``font-family`` anywhere, so the old assertion failed on the
    declared minimum while the property it stood for held perfectly. The minimums
    CI job is what caught that.

    One element per drawn label, and no ``<use>``: that is the pair that separates
    this mode from ``svg_fonttype="path"`` on every version.
    """
    result = render_sankey(nodes, links, wide_enough)
    path = tmp_path / "diagram.svg"
    save(result, str(path))
    body = path.read_text()
    assert body.count("<text") == len(result.labels)
    assert "<use" not in body, "glyphs were referenced rather than written as text"


def test_svg_can_embed_glyph_outlines_instead(nodes, links, wide_enough, tmp_path):
    """The opposite mode: glyphs become outlines, so no text element survives.

    Deliberately does **not** assert that the label strings are absent, tempting as
    that reads. matplotlib writes each string into an SVG comment next to the glyph
    references, so the text is still findable in the file and an absence check would
    fail for a reason that has nothing to do with this setting. What changes is
    whether the text is a rendered element, so that is what gets checked.

    The old assertion here inverted the same ``font-family`` grep, which passes
    vacuously on any matplotlib that never writes that attribute.
    """
    config = {**wide_enough, "svg_fonttype": "path"}
    result = render_sankey(nodes, links, config)
    path = tmp_path / "outlined.svg"
    save(result, str(path), config)
    body = path.read_text()
    assert result.labels, "no labels were drawn, so this would pass vacuously"
    assert "<text" not in body
    assert "<use" in body, "glyphs should be outlines referenced by use elements"


def test_pdf_is_written(nodes, links, wide_enough, tmp_path):
    result = render_sankey(nodes, links, wide_enough)
    path = tmp_path / "diagram.pdf"
    save(result, str(path))
    assert path.read_bytes().startswith(b"%PDF")


def test_ribbon_thickness_is_proportional_to_flow(nodes, links, wide_enough):
    result = render_sankey(nodes, links, wide_enough)
    shapes = result.as_dict()["links"]
    scale = result.frame.px_per_unit
    for shape in shapes:
        assert shape["height"] == pytest.approx(shape["flow"] * scale)


def test_ribbons_are_inset_from_their_nodes(nodes, links, wide_enough):
    result = render_sankey(nodes, links, wide_enough)
    resolved = result.as_dict()
    inset = result.config["link_inset_px"]
    width = result.config["node_width_px"]
    for shape in resolved["links"]:
        source_rect = resolved["nodes"][shape["from"]]["rect"]
        target_rect = resolved["nodes"][shape["to"]]["rect"]
        assert shape["x"] == pytest.approx(source_rect[0] + width + inset)
        assert shape["x2"] == pytest.approx(target_rect[0] - inset)


def test_uncoloured_nodes_still_render(links, tmp_path):
    """With no node specs at all, keys stand in as labels.

    The gutter is measured from the widest first-column key rather than fixed,
    for the same reason ``wide_enough`` measures rather than hardcodes: a constant
    here silently encodes how long one dataset's source key happens to be, and
    fails on the next dataset for a reason that has nothing to do with colour.
    """
    keys = {link["from"] for link in links} | {link["to"] for link in links}
    widest = max((k for k in keys if k.startswith("src:")), key=len)
    result = render_sankey({}, links, {"label_gutter_px": text_width(widest) + 20})
    path = tmp_path / "plain.svg"
    save(result, str(path))
    assert path.exists()


def test_identical_input_produces_identical_svg(nodes, links, wide_enough, tmp_path):
    """Reproducibility holds within one matplotlib version, which is what a
    content hash over generated documents needs."""
    digests = []
    for name in ("first.svg", "second.svg"):
        result = render_sankey(nodes, links, wide_enough)
        path = tmp_path / name
        save(result, str(path))
        digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert digests[0] == digests[1]


def test_link_order_decides_ties(wide_enough):
    """Input order is the last tie-break, not a general reordering.

    It only decides between links the earlier criteria cannot separate, so it
    takes equal flows to see it. Documented behaviour, inherited deliberately
    from the reference implementation.
    """
    equal = [
        {"from": "s", "to": "a", "flow": 100},
        {"from": "s", "to": "b", "flow": 100},
        {"from": "a", "to": "t", "flow": 100},
        {"from": "b", "to": "t", "flow": 100},
    ]
    forward = render_sankey({}, equal, {"label_gutter_px": 40}).layout
    backward = render_sankey({}, list(reversed(equal)), {"label_gutter_px": 40}).layout
    assert forward.nodes["a"].y < forward.nodes["b"].y
    assert backward.nodes["b"].y < backward.nodes["a"].y


def test_link_order_matters_exactly_where_the_chain_ties(
    nodes, links, wide_enough, order_sensitive
):
    """The flip side, pinned in both directions across all five datasets.

    Reversing the link list is expected to change the diagram only for a dataset
    whose tie-break chain actually runs out of criteria. Which datasets those are
    is recorded per dataset rather than guessed, because the intuitive rule is
    wrong: it is *not* the ones with equal sibling flows. See ``order_sensitive``
    in conftest for why the two come apart.

    Asserting the insensitive case matters because it is what real data usually
    falls into — a reordered query result must not silently redraw the diagram.
    Asserting the sensitive case matters because it is what stops the tie-break
    chain being collapsed into a single sort key.
    """
    a = render_sankey(nodes, links, wide_enough).as_dict()
    b = render_sankey(nodes, list(reversed(links)), wide_enough).as_dict()
    if order_sensitive:
        assert a["nodes"] != b["nodes"], (
            "declared order-sensitive, but reversing the links changed nothing"
        )
    else:
        assert a["nodes"] == b["nodes"]


# --------------------------------------------------------------------------- #
# Embedding
# --------------------------------------------------------------------------- #


def _embed(nodes, links, config, width, height):
    """Draw into a figure of our own making, the way a host page would."""
    figure = Figure(figsize=(width / 72.0, height / 72.0), dpi=72)
    ax = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    return ax, draw_sankey(ax, nodes, links, config)


def test_embedded_geometry_matches_a_standalone_render(nodes, links, wide_enough):
    """The whole point of the seam: same input, same diagram, either entry point.

    Compares resolved geometry rather than pixels, which is the comparison that
    survives a matplotlib upgrade.
    """
    standalone = render_sankey(nodes, links, wide_enough)
    _, embedded = _embed(
        nodes, links, wide_enough, standalone.frame.width, standalone.frame.height
    )
    assert embedded.as_dict() == standalone.as_dict()


def test_embedding_draws_the_same_artists(nodes, links, wide_enough):
    """Identical geometry would also be reported by a function that drew nothing."""
    standalone = render_sankey(nodes, links, wide_enough)
    host, _ = _embed(
        nodes, links, wide_enough, standalone.frame.width, standalone.frame.height
    )
    theirs = standalone.figure.axes[0]
    assert len(host.patches) == len(theirs.patches)
    assert len(host.texts) == len(theirs.texts)
    assert len(host.patches) > 0


def test_draw_sankey_sets_the_pixel_contract_itself(nodes, links, wide_enough):
    """A host that gets the limits wrong would rescale the diagram silently, so
    draw_sankey does not let the host set them at all."""
    frame = build_frame(nodes, links, wide_enough)
    figure = Figure(figsize=(4, 3), dpi=72)  # deliberately the wrong shape
    ax = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(-17.0, 3.0)
    ax.set_ylim(-4.0, 900.0)  # and upside down

    draw_sankey(ax, nodes, links, wide_enough)

    assert ax.get_xlim() == (0.0, frame.width)
    assert ax.get_ylim() == (frame.height, 0.0)  # y downward
    assert not ax.axison


def test_embedding_leaves_the_host_surface_alone(nodes, links, wide_enough):
    """An embedded diagram sits on a surface its host already painted, so it must
    not paint one of its own — while a figure it owns still gets its background.

    background_color is set here and deliberately differs from the host's surface:
    in the embedded path it is only meant to feed link_flatten_alpha, so if
    draw_sankey painted it the host's colour would be gone.
    """
    config = {**wide_enough, "background_color": "#FFFFFF"}

    figure = Figure(figsize=(900 / 72.0, 360 / 72.0), dpi=72)
    host = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    host.set_facecolor("#F0F4F6")  # the host's own card surface
    draw_sankey(host, nodes, links, config)
    assert host.get_facecolor() == pytest.approx((240 / 255, 244 / 255, 246 / 255, 1.0))

    owned = render_sankey(nodes, links, config)
    assert owned.figure.axes[0].get_facecolor() == (1.0, 1.0, 1.0, 1.0)


def test_build_frame_reports_the_width_before_anything_is_drawn(nodes, links):
    """What an embedder calls it for: the gutter and preserve_column_pitch both
    move the final width, so the box cannot be allotted from width_px alone."""
    config = {"width_px": 900, "label_gutter_px": 200}
    widened = build_frame(nodes, links, config)
    assert widened.width == pytest.approx(1097)

    exact = build_frame(nodes, links, {**config, "preserve_column_pitch": False})
    assert exact.width == pytest.approx(900)
