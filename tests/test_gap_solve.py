"""The node gap must render at exactly the requested pixel height.

This needs no fixture: it is a property of the solve. It is also the regression
test for a specific mistake — converting pixels to flow units with the scale from
*before* gaps were added, when the gap is drawn against the scale from after.
"""

from __future__ import annotations

import pytest

from sankey_mpl import compute_layout, render_sankey

PLOT_HEIGHT = 354.0

# A second shape, deliberately deeper in one column than the example, so the slot
# count differs and the error the naive formula makes is larger.
DENSE_LINKS = [
    {"from": "root", "to": f"mid{i}", "flow": flow}
    for i, flow in enumerate([900, 700, 500, 300, 100, 60, 40, 20, 10, 5])
] + [
    {"from": f"mid{i}", "to": "leaf", "flow": flow}
    for i, flow in enumerate([900, 700, 500, 300, 100, 60, 40, 20, 10, 5])
]


@pytest.mark.parametrize("gap_px", [0.0, 0.5, 1.0, 3.13274336, 4.5, 8.0, 12.0])
def test_requested_gap_is_rendered_exactly(nodes, links, gap_px):
    result = render_sankey(nodes, links, {"node_gap_px": gap_px})
    assert result.as_dict()["rendered_gap_px"] == pytest.approx(gap_px, abs=1e-9)


@pytest.mark.parametrize("gap_px", [0.5, 2.0, 4.5, 9.0])
def test_requested_gap_is_rendered_exactly_on_a_dense_graph(gap_px):
    result = render_sankey({}, DENSE_LINKS, {"node_gap_px": gap_px})
    assert result.as_dict()["rendered_gap_px"] == pytest.approx(gap_px, abs=1e-9)


def test_a_zero_gap_leaves_the_height_untouched(nodes, links):
    layout = compute_layout(nodes, links, gap_px=0.0, plot_height=PLOT_HEIGHT)
    assert layout.gap_units == 0.0
    assert layout.total_height == pytest.approx(layout.total_height_unpadded)


def test_the_naive_conversion_would_undershoot(nodes, links):
    """Documents why the solve is not a single division.

    Converting with the pre-gap scale gives a gap that renders short, and short by
    more the more gaps there are. Kept as a test so nobody 'simplifies' the solve
    back into the bug.
    """
    gap_px = 4.5
    layout = compute_layout(nodes, links, gap_px=gap_px, plot_height=PLOT_HEIGHT)

    naive_units = gap_px * layout.total_height_unpadded / PLOT_HEIGHT
    slots = layout.gap_slots_at_max
    naive_total = layout.total_height_unpadded + slots * naive_units
    naive_rendered = naive_units * PLOT_HEIGHT / naive_total

    assert naive_rendered < gap_px - 0.05, (
        "the naive conversion is supposed to undershoot; if this fails the "
        "arithmetic has changed"
    )
    # And the real solve does not.
    assert layout.gap_units * PLOT_HEIGHT / layout.total_height == pytest.approx(
        gap_px, abs=1e-9
    )


def test_a_gap_too_large_to_fit_is_refused(nodes, links):
    with pytest.raises(ValueError, match="does not fit"):
        render_sankey(nodes, links, {"node_gap_px": 200.0})


def test_gap_scales_with_the_plot_height(nodes, links):
    """Same requested gap, taller plot: still exact, but fewer flow units per px."""
    short = compute_layout(nodes, links, gap_px=4.5, plot_height=200.0)
    tall = compute_layout(nodes, links, gap_px=4.5, plot_height=800.0)
    assert short.gap_units * 200.0 / short.total_height == pytest.approx(4.5, abs=1e-9)
    assert tall.gap_units * 800.0 / tall.total_height == pytest.approx(4.5, abs=1e-9)
    assert tall.gap_units < short.gap_units
