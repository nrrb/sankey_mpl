# Contributing

Thanks for looking. This file is the short version of what a change here has to
respect. Several things in `layout.py` look like mistakes and are not, so the
[Load-bearing decisions](#load-bearing-decisions) section is worth reading before
simplifying anything.

## Setup

```
pip install -e ".[dev]"
```

Then the three checks CI runs, all of which must pass:

```
ruff check . && ruff format --check .
mypy
pytest -q --cov=sankey_mpl
```

`pytest` takes about a minute, because most of the cost is the render tests and those
run once per dataset. `pytest -k catday` narrows to one shape while iterating.

Node is needed only to regenerate the golden geometry, and only if you change a
dataset. CI never runs it.

```
cd tools && npm install && node generate_golden.mjs   # goldens (needs Node)
python tools/render_previews.py                       # gallery images (no Node)
```

## How the tests are organised

Split by whether the library's deliberate differences from the reference affect the
quantity under test. Preserve that split when adding tests.

| File | Covers |
|---|---|
| `test_layout.py` | Geometry against the golden, in two groups: quantities that hold for any configuration, and quantities that only match once the node gap is set to the reference's own value |
| `test_gap_solve.py` | The gap solve as a property. Needs no fixture |
| `test_guards.py` | One test per refusal |
| `test_render.py` | Drawing: vector output, label rules, figure dimensions, determinism, embedding |

The whole suite is parametrised over five datasets of deliberately different shapes,
so a change that breaks only one shape still fails. `tests/data/datasets.json` records
what each dataset is for, and each spec in `tools/datasets/` opens with a comment
explaining which properties it was built to exercise.

**A constant in a test that came from one dataset's dimensions is a latent failure for
the next dataset.** Two tests had to stop hardcoding numbers when the suite went from
one dataset to five. Measure instead: `text_width()` exists for exactly this.

## Rules about the fixtures

- **Never regenerate a golden from this library's own output.** A golden produced by
  the code under test proves only that the code agrees with itself. They come from
  `tools/generate_golden.mjs`, which runs the real JavaScript library.
- **Keep the datasets synthetic.** The subject matter is comical on purpose; the
  numbers are not. Each flow was chosen to hit a code path and named for a laugh
  afterwards. Do not tune one to look plausible, and do not derive one from real data.
- A new dataset needs: exactly one column-0 node, flow conserved end to end, at least
  one node thin enough to trip the label drop rule at the default 900x360, a short
  `src:` label, and the `src:` key prefix. The first two are what let `conftest.py`
  derive the parity configuration instead of hardcoding it.

## Load-bearing decisions

Each of these looks like something to clean up. Each has a reason, and most have a
test whose only job is to stop someone undoing it.

- **Vertical order inside a column is not a sort.** It emerges from the traversal, and
  `_resolve_overlaps` only fixes collisions afterwards. Two nodes can end up in an
  order no sort key would produce. This mirrors the reference.
- **The tie-break chain is a sequence of stable sorts, not one combined key.** Because
  each criterion is a separate stable sort, the residual order a tied sort leaves
  behind is the input order, so input order can decide the outcome whenever *any*
  criterion ties. Collapsing the chain into a single key changes the geometry. The
  `orderSensitive` field on each dataset is what catches it.
- **The `1e-6` epsilon in `layout.py` matters.** It keeps sibling subtrees from
  starting at the same coordinate. Rounding it away changes which of two tied nodes
  lands on top.
- **The node gap is solved, not divided.** The obvious formula converts pixels using
  the scale before gaps are added, but the gap is drawn against the scale after, which
  is smaller because the gaps made the diagram taller.
  `test_gap_solve.py::test_the_naive_conversion_would_undershoot` exists to stop the
  revert.
- **Bad input raises rather than drawing something misleading.** Cycles, backward
  links, disconnected graphs and nodes shorter than their own links all refuse.
- **Ribbon gradients are exact curve subdivisions, not sampled points and not images.**
  A clipped image per ribbon would rasterise, which would defeat the whole point; a
  chord approximation would visibly facet the outline.
- **One data unit is one point is one pixel.** That contract is why `*_px` config keys
  need no conversion. Passing `bbox_inches="tight"` or `pad_inches` to `savefig`, or
  resizing the figure afterwards, invalidates every pixel value in the config.

## Things that will surprise you

- **Determinism holds within one matplotlib version, not across versions.** Do not
  commit a golden `.svg` and diff against it. Compare resolved geometry from
  `as_dict()`, which this library computes and is therefore stable.
- **matplotlib cannot read WOFF or WOFF2.** An unregistered font family falls back
  silently, and that changes layout here rather than only appearance, because the
  gutter check and the collision pass both measure text.
- **Label separation is per-column.** It cannot see a collision between a
  right-pointing label in one column and a left-pointing one in the next, which is the
  pair the default label side mode creates either side of the plot middle. There is no
  assertion for it, because some data cannot avoid it at any sane width. `docs/usage.md`
  has a snippet for checking your own data.
- **When you add a top-level file, add it to the sdist `include` list** in
  `pyproject.toml`. That list is explicit, so a new file is omitted by default. Check
  with `python -m build --sdist && tar -tzf dist/*.tar.gz`.

## Releasing

The version lives in exactly one place, `__version__` in
`src/sankey_mpl/__init__.py`, which is what `[tool.hatch.version]` reads.

```
python tools/bump_version.py <major|minor|patch>
```

That updates `__version__` and `CHANGELOG.md` together, and refuses if the
`[Unreleased]` section is empty. Then commit, tag `vX.Y.Z`, and push the tag: the
publish workflow refuses to publish unless the tag, `__version__` and the changelog all
agree.

**Treat any change to resolved geometry as breaking**, even with an untouched API. A
diagram that moves is a broken diagram for anyone diffing rendered output.

A tag must contain the publish workflow, since GitHub resolves a dispatched workflow on
the ref you select. Add release tooling first, then tag.
