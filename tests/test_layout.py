"""Layout against the reference geometry.

Split by whether the library's deliberate differences from the reference affect
the quantity under test. The first group holds for any configuration; the second
only once the node gap is set to the reference's own value.
"""

from __future__ import annotations

import pytest

from sankey_mpl import compute_layout, render_sankey

PIXEL_TOLERANCE = 0.5


def _layout(nodes, links, gap_px=4.5, plot_height=354.0):
    return compute_layout(nodes, links, gap_px=gap_px, plot_height=plot_height)


# --------------------------------------------------------------------------- #
# Independent of the library's deviations
# --------------------------------------------------------------------------- #


def test_every_node_lands_in_the_reference_column(nodes, links, golden):
    layout = _layout(nodes, links)
    assert layout.max_column == golden["maxColumn"]
    for key, expected in golden["nodes"].items():
        assert layout.nodes[key].column == expected["column"], key


def test_node_sizes_match(nodes, links, golden):
    layout = _layout(nodes, links)
    for key, expected in golden["nodes"].items():
        assert layout.nodes[key].size == pytest.approx(expected["size"]), key


def test_vertical_order_within_each_column_matches(nodes, links, golden):
    """Order, not position: this holds whatever the gap is."""
    layout = _layout(nodes, links)
    for column in range(layout.max_column + 1):
        ours = [
            node.key
            for node in sorted(
                (n for n in layout.nodes.values() if n.column == column),
                key=lambda n: n.y,
            )
        ]
        theirs = [
            key
            for key, node in sorted(
                (
                    (key, node)
                    for key, node in golden["nodes"].items()
                    if node["column"] == column
                ),
                key=lambda item: item[1]["y"],
            )
        ]
        assert ours == theirs, f"column {column}"


def test_link_offsets_match(nodes, links, golden):
    """Offsets are in flow units, so they are gap-independent."""
    layout = _layout(nodes, links)
    for index, expected in enumerate(golden["links"]):
        source = layout.nodes[expected["from"]]
        offset = layout.link_offset(source, "outgoing", expected["to"], index)
        assert offset == pytest.approx(expected["offset"]), (
            f"link {index}: {expected['from']} -> {expected['to']}"
        )


def test_height_before_gaps_is_the_conserved_total(nodes, links, golden):
    layout = _layout(nodes, links)
    source = next(node for node in golden["nodes"].values() if node["column"] == 0)
    assert layout.total_height_unpadded == pytest.approx(
        max(source["inflow"], source["outflow"])
    )


def test_gap_slot_count_matches_the_reference(nodes, links, golden_gap_slots):
    layout = _layout(nodes, links)
    assert layout.gap_slots_at_max == golden_gap_slots


# --------------------------------------------------------------------------- #
# Once the gap matches the reference's, so does everything else
# --------------------------------------------------------------------------- #


def test_total_height_matches_at_the_reference_gap(nodes, links, golden, parity_config):
    result = render_sankey(nodes, links, parity_config)
    assert result.layout.total_height == pytest.approx(golden["totalHeight"], abs=1e-6)


def test_scale_matches_at_the_reference_gap(nodes, links, golden, parity_config):
    result = render_sankey(nodes, links, parity_config)
    area = golden["chartArea"]
    assert result.frame.px_per_unit == pytest.approx(
        (area["bottom"] - area["top"]) / golden["totalHeight"]
    )


def test_node_rectangles_match_at_the_reference_gap(nodes, links, golden, parity_config):
    result = render_sankey(nodes, links, parity_config)
    resolved = result.as_dict()["nodes"]
    for key, expected in golden["nodes"].items():
        ours = resolved[key]
        assert ours["y"] == pytest.approx(expected["y"], abs=1e-6), f"{key} y (units)"


def test_ribbon_geometry_matches_at_the_reference_gap(
    nodes, links, golden, parity_config
):
    result = render_sankey(nodes, links, parity_config)
    ours = result.as_dict()["links"]
    for index, expected in enumerate(golden["links"]):
        label = f"link {index}: {expected['from']} -> {expected['to']}"
        for field in ("x", "x2", "y", "y2", "height"):
            assert ours[index][field] == pytest.approx(
                expected[field], abs=PIXEL_TOLERANCE
            ), f"{label} {field}"
