"""Drawing behaviour: vector output, label rules, figure dimensions."""

from __future__ import annotations

import hashlib

import pytest

from sankey_mpl import render_sankey, save, text_width


@pytest.fixture
def wide_enough(nodes) -> dict:
    """A gutter that fits the example's longest first-column label.

    Deliberately computed rather than hardcoded: the default gutter is sized for a
    typical label, and this fixture's longest one is near the limit, so a
    hardcoded number here would break whenever the example data or the font
    changes.
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


def test_labels_all_point_left_by_default(nodes, links, wide_enough):
    result = render_sankey(nodes, links, wide_enough)
    assert {label["side"] for label in result.labels} == {"left"}


def test_outside_mode_puts_early_columns_on_the_right(nodes, links, wide_enough):
    result = render_sankey(nodes, links, {**wide_enough, "label_side_mode": "outside"})
    assert {label["side"] for label in result.labels} == {"left", "right"}


def test_collision_separation_enforces_the_line_height(nodes, links, wide_enough):
    config = {**wide_enough, "min_label_height_px": 0}
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

    assert smallest_gap(crowded) < 14.4
    assert smallest_gap(spaced) == pytest.approx(14.4, abs=1e-6)


def test_separation_preserves_label_order(nodes, links, wide_enough):
    """Within a column. Separation is per-column, so it can and does reorder
    labels relative to labels in *other* columns — that is not a violation."""
    config = {**wide_enough, "min_label_height_px": 0}
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
    result = render_sankey(nodes, links, wide_enough)
    path = tmp_path / "diagram.svg"
    save(result, str(path))
    assert "font-family" in path.read_text()


def test_svg_can_embed_glyph_outlines_instead(nodes, links, wide_enough, tmp_path):
    result = render_sankey(nodes, links, {**wide_enough, "svg_fonttype": "path"})
    path = tmp_path / "outlined.svg"
    save(result, str(path), {**wide_enough, "svg_fonttype": "path"})
    assert "font-family" not in path.read_text()


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
    result = render_sankey({}, links, {"label_gutter_px": 60})
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


def test_distinct_flows_are_insensitive_to_link_order(nodes, links, wide_enough):
    """The flip side: with no ties to break, order does not matter.

    Worth pinning, because it is the case real data usually falls into and it
    means a reordered query result does not silently redraw the diagram.
    """
    a = render_sankey(nodes, links, wide_enough).as_dict()
    b = render_sankey(nodes, list(reversed(links)), wide_enough).as_dict()
    assert a["nodes"] == b["nodes"]
