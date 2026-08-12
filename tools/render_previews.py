#!/usr/bin/env python3
"""Render a preview of each dataset for the README gallery.

    python tools/render_previews.py

Writes ``examples/<key>.svg`` and ``examples/<key>.png`` for every dataset in
``tests/data/datasets.json``.

Unlike ``generate_golden.mjs`` this needs no Node: it renders with this library,
which is the point — the gallery should show what the library produces, and the
goldens next door are what check that against the reference. Nothing here feeds
back into the test fixtures.

Two choices worth knowing about:

* **An opaque background is baked in.** The library defaults to transparent so a
  diagram composites onto whatever page it lands on, which is right for a library
  default and wrong for a README: GitHub serves the same image to light and dark
  readers, and the default label colour would vanish against a dark one. The
  surface used here is the one the palette was validated against.
* **Both formats are written.** The PNG is what the README embeds, because
  GitHub's markdown rendering of large SVGs is inconsistent. The SVG is committed
  next to it because genuinely scalable vector output is the library's whole
  selling point, and an unopenable claim is worth less than an inspectable one.
"""

from __future__ import annotations

import json
from pathlib import Path

from sankey_mpl import render_sankey, save, text_width

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "data"
OUT = ROOT / "examples"

# The light surface the categorical palette was validated against for
# colour-vision-deficiency separation and contrast. Changing it invalidates that
# check, so re-run the validator if you do.
SURFACE = "#FCFCFB"

# Raster scale for the PNG. 2x keeps the gallery crisp on a high-density display
# without committing files several megabytes each.
PREVIEW_DPR = 2


def preview_config(nodes: dict, preview: dict) -> dict:
    """Config for one preview, sized from that dataset's ``preview`` block.

    Deliberately *not* the dataset's ``render`` block: that is what the golden was
    produced at, so treating it as a display size would mean cosmetic tweaks moved
    test geometry.
    """
    # The gutter has to clear the widest first-column label or the guard refuses
    # to draw. Every other column's labels sit in the pitch between columns,
    # which is why the preview widths are generous.
    widest = max(
        (spec.get("label", key) for key, spec in nodes.items() if key.startswith("src:")),
        key=text_width,
    )
    return {
        "width_px": preview["width"],
        "height_px": preview["height"],
        "device_pixel_ratio": PREVIEW_DPR,
        "background_color": SURFACE,
        "label_gutter_px": text_width(widest) + 24,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((DATA / "datasets.json").read_text())["datasets"]

    for entry in manifest:
        key = entry["key"]
        data = json.loads((DATA / f"{key}.json").read_text())

        config = preview_config(data["nodes"], entry["preview"])
        result = render_sankey(data["nodes"], data["links"], config)

        for suffix in ("svg", "png"):
            save(result, str(OUT / f"{key}.{suffix}"))

        print(
            f"{key:10} {result.frame.width:>6.0f}x{result.frame.height:<5.0f} "
            f"{len(result.labels):>3} labels, {len(result.labels_dropped):>2} dropped"
        )


if __name__ == "__main__":
    main()
