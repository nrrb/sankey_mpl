"""Saving, with output that is byte-for-byte reproducible.

matplotlib does not produce identical bytes across runs by default: element ids
in SVG derive from object identity, and every format embeds a creation
timestamp. Both are fixed here, which is what makes a golden-file test possible
and keeps a document's content hash stable when it is regenerated unchanged.

One limit worth knowing: reproducibility holds for a given matplotlib version,
not across versions. matplotlib changes its own output between releases, so pin
the version if you intend to compare bytes over time, and compare two renders in
one process rather than against a stored file.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from matplotlib import rc_context
from matplotlib.figure import Figure

from .config import merge_config
from .render import SankeyFigure, parse_color

__all__ = ["save"]

# Each format embeds its timestamp under a different key.
_TIMESTAMP_KEY = {"svg": "Date", "pdf": "CreationDate"}


def save(
    figure: SankeyFigure | Figure,
    path: str,
    config: Mapping[str, Any] | None = None,
) -> None:
    """Write ``figure`` to ``path``, inferring the format from the extension.

    Supports the formats matplotlib does; ``.svg``, ``.pdf`` and ``.png`` are the
    ones this library is set up for. Never pass ``bbox_inches`` or ``pad_inches``
    to matplotlib yourself for one of these figures: either one resizes the
    figure box and breaks the one-unit-is-one-pixel contract, so the diagram no
    longer lands at the dimensions it was configured for.
    """
    if isinstance(figure, SankeyFigure):
        # Prefer the config the figure was drawn with, so a caller who passes
        # nothing still gets the right background and font handling.
        merged = merge_config(config) if config is not None else dict(figure.config)
        target = figure.figure
    else:
        merged = merge_config(config)
        target = figure

    fmt = path.rsplit(".", 1)[-1].lower()
    kwargs: dict[str, Any] = {"format": fmt, "dpi": target.dpi}
    key = _TIMESTAMP_KEY.get(fmt)
    if key is not None:
        kwargs["metadata"] = {key: None}
    if merged["background_color"] is None:
        kwargs["transparent"] = True
    else:
        kwargs["facecolor"] = parse_color(merged["background_color"])

    with rc_context(
        {
            "svg.hashsalt": merged["svg_hashsalt"],
            "svg.fonttype": merged["svg_fonttype"],
            "pdf.fonttype": merged["pdf_fonttype"],
            "ps.fonttype": merged["ps_fonttype"],
        }
    ):
        target.savefig(path, **kwargs)
