"""Shared fixtures.

The golden data in ``tests/data`` was produced by running the reference
JavaScript implementation (``tools/generate_golden.mjs``), so comparing against
it is a genuine check rather than this library agreeing with itself.

Three of the library's defaults deliberately differ from the reference and move
geometry: the node gap, the label gutter, and the label side rule. Tests that
compare pixel positions therefore run under ``parity_config``, which puts those
three back. Tests of the defaults' own behaviour do not use it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def example() -> dict:
    return json.loads((DATA / "example.json").read_text())


@pytest.fixture(scope="session")
def nodes(example: dict) -> dict:
    return example["nodes"]


@pytest.fixture(scope="session")
def links(example: dict) -> list:
    return example["links"]


@pytest.fixture(scope="session")
def golden() -> dict:
    return json.loads((DATA / "golden-layout.json").read_text())


@pytest.fixture(scope="session")
def golden_gap_slots(golden: dict) -> int:
    """How many gap quanta sit above the node that sets the reference's height.

    Derived from the golden alone. The reference sizes its gap as
    ``height_before / backing_store_height * node_padding``, and for a graph that
    conserves flow the height before gaps is just the source node's total, so the
    quantum and hence the count both fall out of the recorded numbers.
    """
    render = golden["render"]
    source = next(node for node in golden["nodes"].values() if node["column"] == 0)
    height_before = max(source["inflow"], source["outflow"])
    quantum = height_before / render["backingStoreHeight"] * render["nodePadding"]
    slots = (golden["totalHeight"] - height_before) / quantum
    assert abs(slots - round(slots)) < 1e-6, "gap slot count is not an integer"
    return round(slots)


@pytest.fixture(scope="session")
def parity_gap_px(golden: dict, golden_gap_slots: int) -> float:
    """The gap, in pixels, that the reference's own formula worked out to.

    Substituting the reference's gap quantum into ``gap * plot_height / total``
    cancels the flow totals out entirely, leaving a closed form in the render
    settings and the slot count.
    """
    render = golden["render"]
    padding = render["padding"]
    plot_height = render["cssHeight"] - padding["top"] - padding["bottom"]
    return (
        render["nodePadding"]
        * plot_height
        / (render["backingStoreHeight"] + golden_gap_slots * render["nodePadding"])
    )


@pytest.fixture(scope="session")
def parity_config(golden: dict, parity_gap_px: float) -> dict:
    """Configuration that reproduces the reference's geometry exactly."""
    render = golden["render"]
    padding = render["padding"]
    return {
        "width_px": render["cssWidth"],
        "height_px": render["cssHeight"],
        "device_pixel_ratio": render["devicePixelRatio"],
        "pad_top": padding["top"],
        "pad_bottom": padding["bottom"],
        "pad_right": padding["right"],
        # Collapse the gutter so horizontal positions line up with the reference,
        # which reserves only 3px on the left.
        "label_gutter_px": padding["left"],
        "preserve_column_pitch": False,
        "node_width_px": render["nodeWidth"],
        "node_gap_px": parity_gap_px,
        "link_inset_px": render["borderWidth"] / 2.0 + 0.5,
        # The reference has no drop rule and no collision handling.
        "label_side_mode": "outside",
        "min_label_height_px": 0,
        "label_collision_separation": False,
    }
