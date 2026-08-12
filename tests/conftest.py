"""Shared fixtures.

The golden data in ``tests/data`` was produced by running the reference
JavaScript implementation (``tools/generate_golden.mjs``), so comparing against
it is a genuine check rather than this library agreeing with itself.

Every fixture here is parametrised over all five datasets, so a test that takes
``nodes``, ``links`` or ``golden`` automatically runs against each of them. The
five are deliberately different shapes — dense sharing, a conserved time budget,
a pure tree, a convergent funnel, and one with tied flows — because several code
paths only appear in one of them. ``tests/data/datasets.json`` records what each
is for.

Three of the library's defaults deliberately differ from the reference and move
geometry: the node gap, the label drop rule, and the label separation pass. Tests
that compare pixel positions therefore run under ``parity_config``, which puts
those three back. Tests of the defaults' own behaviour do not use it.

The label *side* rule and the gutter used to be on that list and are not any more:
the default is now the reference's own outward-pointing rule with a hairline gutter,
so ``parity_config`` setting them is redundant rather than corrective. They are left
in it deliberately, since a parity configuration that spells out what it depends on
does not silently stop being parity when a default moves again.

Nothing here hardcodes a number that the data could supply instead. Each
dataset's ``parity_config`` is derived from its own golden, so adding or changing
a dataset needs no edits in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"

MANIFEST = json.loads((DATA / "datasets.json").read_text())["datasets"]
KEYS = [entry["key"] for entry in MANIFEST]


@pytest.fixture(scope="session", params=KEYS)
def dataset(request: pytest.FixtureRequest) -> dict:
    """One of the five datasets, with its input and its golden geometry."""
    key = request.param
    data = json.loads((DATA / f"{key}.json").read_text())
    return {
        "key": key,
        "title": data["title"],
        "nodes": data["nodes"],
        "links": data["links"],
        "golden": json.loads((DATA / f"{key}-golden.json").read_text()),
    }


@pytest.fixture(scope="session")
def nodes(dataset: dict) -> dict:
    return dataset["nodes"]


@pytest.fixture(scope="session")
def links(dataset: dict) -> list:
    return dataset["links"]


@pytest.fixture(scope="session")
def golden(dataset: dict) -> dict:
    return dataset["golden"]


@pytest.fixture(scope="session")
def order_sensitive(dataset: dict) -> bool:
    """Whether reversing this dataset's link list changes its layout.

    Declared per dataset in ``tools/datasets/*.json`` rather than computed, and
    deliberately so: computing it would mean asking the layout whether the layout
    agrees with itself, which proves nothing. Pinned as data, it fails loudly when
    a change to the tie-break chain flips a dataset from one category to the other.

    Do not reach for equal sibling flows as a proxy for this — the two come apart.
    ``catday`` has no two sibling links of equal flow yet is order-sensitive,
    because two of its activity nodes tie on subtree size *and* degree, and the
    chain is a sequence of stable sorts rather than one combined key, so the
    residual order those tied sorts leave behind is the input order. ``sourdough``
    is the mirror image: equal sibling flows that subtree size resolves before flow
    is ever compared, and no sensitivity at all.
    """
    return next(e for e in MANIFEST if e["key"] == dataset["key"])["orderSensitive"]


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
