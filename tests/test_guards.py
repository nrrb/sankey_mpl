"""Inputs the library refuses.

Every case here is one the reference implementation handles by doing something
surprising instead — looping a ribbon over the top of the canvas, force-placing a
node to break a cycle, overlapping ribbons on a node too short to hold them. This
library refuses, so that data which would render misleadingly fails loudly.
"""

from __future__ import annotations

import pytest

from sankey_mpl import compute_layout, render_sankey


def test_empty_links():
    with pytest.raises(ValueError, match="nothing to lay out"):
        compute_layout({}, [], gap_px=4.5, plot_height=354.0)


def test_missing_link_field():
    with pytest.raises(ValueError, match="'flow'"):
        compute_layout({}, [{"from": "a", "to": "b"}], gap_px=4.5, plot_height=354.0)


def test_negative_flow():
    with pytest.raises(ValueError, match="negative flow"):
        compute_layout(
            {}, [{"from": "a", "to": "b", "flow": -1}], gap_px=4.5, plot_height=354.0
        )


def test_cycle():
    """A closed loop is refused.

    Two guards can catch this and which one fires depends on the shape. A simple
    ring gets an arbitrary entry point elected into column 0, so the levelling
    succeeds and the forward-link check is what rejects it. Either message is a
    correct refusal, so the test accepts both rather than pinning the route.
    """
    cycle = [
        {"from": "a", "to": "b", "flow": 1},
        {"from": "b", "to": "c", "flow": 1},
        {"from": "c", "to": "a", "flow": 1},
    ]
    with pytest.raises(ValueError, match="cycle|forward"):
        compute_layout({}, cycle, gap_px=4.5, plot_height=354.0)


def test_backward_link():
    """A link that would need to travel leftward between columns."""
    backward = [
        {"from": "a", "to": "b", "flow": 5},
        {"from": "b", "to": "c", "flow": 5},
        # c is pushed to the last column, so this one points backward.
        {"from": "c", "to": "b", "flow": 1},
    ]
    with pytest.raises(ValueError, match="cycle|forward"):
        compute_layout({}, backward, gap_px=4.5, plot_height=354.0)


def test_disconnected_components():
    split = [
        {"from": "a", "to": "b", "flow": 1},
        {"from": "c", "to": "d", "flow": 1},
    ]
    with pytest.raises(ValueError, match="not reachable|Disconnected"):
        compute_layout({}, split, gap_px=4.5, plot_height=354.0)


def test_min_size_mode_that_would_overlap_ribbons():
    """`min` can size a node below the total of its own links."""
    unbalanced = [
        {"from": "a", "to": "b", "flow": 10},
        {"from": "b", "to": "c", "flow": 4},
        {"from": "b", "to": "d", "flow": 6},
        {"from": "x", "to": "b", "flow": 20},
    ]
    with pytest.raises(ValueError, match="shorter than the links|cycle|not reachable"):
        compute_layout({}, unbalanced, gap_px=4.5, plot_height=354.0, size_mode="min")


def test_bad_size_mode():
    with pytest.raises(ValueError, match="size_mode"):
        compute_layout(
            {},
            [{"from": "a", "to": "b", "flow": 1}],
            gap_px=4.5,
            plot_height=354.0,
            size_mode="average",
        )


def test_unknown_config_key(nodes, links):
    with pytest.raises(ValueError, match="unknown config keys"):
        render_sankey(nodes, links, {"nodeWidth": 10})


def test_right_padding_too_narrow_for_the_last_column(nodes, links):
    with pytest.raises(ValueError, match="pad_right"):
        render_sankey(nodes, links, {"pad_right": 4})


def test_gutter_too_narrow_for_its_labels(nodes, links):
    with pytest.raises(ValueError, match="label_gutter_px"):
        render_sankey(nodes, links, {"label_gutter_px": 20})


def test_bad_label_side_mode(nodes, links):
    with pytest.raises(ValueError, match="label_side_mode"):
        render_sankey(nodes, links, {"label_side_mode": "inside"})


def test_flatten_alpha_without_a_background(nodes, links):
    with pytest.raises(ValueError, match="background_color"):
        render_sankey(nodes, links, {"link_flatten_alpha": True})


def test_padding_wider_than_the_figure(nodes, links):
    """Widening is what normally absorbs a big gutter, so this needs it off."""
    with pytest.raises(ValueError, match="no room to draw"):
        render_sankey(
            nodes,
            links,
            {"width_px": 100, "label_gutter_px": 200, "preserve_column_pitch": False},
        )


def test_figure_too_short_to_hold_its_padding(nodes, links):
    with pytest.raises(ValueError, match="plot_height must be positive"):
        render_sankey(nodes, links, {"height_px": 6})


def test_figure_too_short_for_the_requested_gaps(nodes, links):
    """Taller than its padding, but not tall enough for the gaps it needs."""
    with pytest.raises(ValueError, match="does not fit"):
        render_sankey(nodes, links, {"height_px": 10})
