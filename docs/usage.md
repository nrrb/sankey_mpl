# Using sankey_mpl

How to drive the library, what every configuration key does, and where it will
push back. If you only read one section, read [The data model](#the-data-model)
and [Labels](#labels). Labels are the only part that needs a decision from you.

- [Install](#install)
- [The data model](#the-data-model)
- [Quick start](#quick-start)
- [API](#api)
- [Configuration](#configuration)
- [The pixel contract](#the-pixel-contract)
- [Labels](#labels)
- [Colour, gradients and alpha](#colour-gradients-and-alpha)
- [Embedding](#embedding)
- [Export](#export)
- [Reproducibility](#reproducibility)
- [Differences from chartjs-chart-sankey](#differences-from-chartjs-chart-sankey)
- [Errors](#errors)
- [Recipes](#recipes)

## Install

```
pip install sankey_mpl
```

Python 3.10+, matplotlib and numpy. Nothing else.

## The data model

Two inputs: **nodes** and **links**.

```python
nodes = {
    "a": {"label": "Group A", "color": "#4C78A8"},
    "b": {"label": "Group B"},  # colour optional
    "c": {},  # label falls back to the key
}
links = [
    {"from": "a", "to": "c", "flow": 120},
    {"from": "b", "to": "c", "flow": 40},
]
```

- **Keys are arbitrary strings.** They identify nodes and never appear in the
  output unless a node has no label. Prefixing by layer (`"stage:paid"`) is a
  handy convention, not a requirement.
- **Nodes are optional metadata.** The graph comes entirely from `links`; a key
  in `nodes` that no link mentions is ignored, and a key in `links` missing from
  `nodes` gets its key as its label and black as its colour. `render_sankey({},
  links)` works.
- **`flow` is any positive number** in any unit: messages, dollars, people. The
  library calls it a *flow unit* and scales the whole diagram so the tallest
  column fits the plot area. Node heights and ribbon thicknesses are all
  proportional to it, on one shared scale, so a unit is the same number of pixels
  in every column.
- **Duplicate pairs are not merged.** Two links with the same `from` and `to`
  become two stacked ribbons. Sum them yourself if you want one.

The graph must be **acyclic and left-to-right**. Columns are derived, not
declared: a node sits one column right of everything feeding it. Nodes with no
incoming link start in column 0, and nodes with no outgoing link are pushed to the
last column so short paths finish flush with long ones (turn that off with
`align_sinks_right`).

### Link order can matter

Worth knowing, because it surprises people: **the order of `links` is the last
tie-break in vertical placement.** Placement inside a column is resolved by a
traversal that compares subtree size, then node degree, then flow; where all three
tie, the order the links were supplied in decides.

In practice that means data with distinct flows is insensitive to order (a
reordered query result draws the same diagram), while genuinely equal flows swap
places if you reverse them. Inherited deliberately from the original
implementation so diagrams match it. Build your link list in a stable order and
the question never arises.

## Quick start

```python
from sankey_mpl import render_sankey, save

result = render_sankey(nodes, links)
save(result, "diagram.svg")
save(result, "diagram.pdf")
save(result, "diagram.png")
```

`render_sankey` returns a `SankeyFigure`. Its `.figure` is an ordinary matplotlib
`Figure`, so it can be embedded, further annotated, or saved with matplotlib
directly, with one caveat; see [Export](#export).

## API

### `render_sankey(nodes, links, config=None) -> SankeyFigure`

Draws the diagram. `config` overrides `DEFAULT_CONFIG`; unknown keys raise rather
than being ignored, so a typo is an error and not a silently unchanged picture.

### `draw_sankey(ax, nodes, links, config=None) -> SankeyDrawing`

Draws into an axes you already have, for embedding the diagram in a larger figure:
a report page, a dashboard, a multi-panel comparison. Same three arguments as
`render_sankey` after the axes. See [Embedding](#embedding) for the four things
that behave differently in this mode, all of which bite silently.

### `build_frame(nodes, links, config=None) -> Frame`

Resolves everything needed to draw (layout, scales, padding) without drawing or
creating a figure. Call it when you need the diagram's final pixel size *before*
choosing where to put it: `label_gutter_px` and `preserve_column_pitch` both feed
into `frame.width`, so the width that comes out is not necessarily the `width_px`
that went in. The merged config comes back on `frame.config`.

### `SankeyFigure` / `SankeyDrawing`

`render_sankey` returns a `SankeyFigure`; `draw_sankey` returns a
`SankeyDrawing`, which is the same thing without `.figure`: a diagram drawn into
someone else's axes does not own a figure.

| Attribute | What it is |
|---|---|
| `.figure` | the matplotlib `Figure` (`SankeyFigure` only) |
| `.layout` | resolved positions in flow units (`SankeyLayout`) |
| `.frame` | the pixel frame: scales, padding, plot area (`Frame`) |
| `.config` | the merged configuration actually used |
| `.labels` | one entry per drawn label: `key`, `side`, `x`, `y`, `text` |
| `.labels_dropped` | keys whose labels were suppressed as unreadable |
| `.as_dict()` | all of the above as plain JSON-friendly data |

`as_dict()` is the introspection hatch. It gives every node's column, vertical
position and pixel rectangle, and every ribbon's endpoints and thickness, useful
for testing, for debugging a layout that looks wrong, and for driving your own
annotations.

### `compute_layout(nodes, links, *, gap_px, plot_height, size_mode="max", align_sinks_right=True) -> SankeyLayout`

The layout on its own, with no matplotlib involved. Use it to inspect or test
positions without rendering, or to drive a different backend. Everything is in
flow units and column indices; `gap_px` and `plot_height` are in pixels because
the gap has to be solved against the final vertical scale.

### `save(figure, path, config=None)`

Writes SVG, PDF or PNG with reproducible bytes. Format comes from the extension.
Accepts a `SankeyFigure` (preferred, since it reuses the config the diagram was
drawn with) or a bare matplotlib `Figure`.

### `text_width(text, config=None) -> float`

Width of a string in pixels, in the configured label font. Use it to size
`label_gutter_px` from your actual data rather than guessing.

## Configuration

Every key, with its default. Override any subset:

```python
render_sankey(nodes, links, {"node_width_px": 14, "link_alpha": 0.7})
```

### Canvas

| Key | Default | Meaning |
|---|---|---|
| `width_px` | `900` | figure width in pixels |
| `height_px` | `360` | figure height in pixels |
| `device_pixel_ratio` | `3` | raster export scale; `dpi = 72 × this`. Never affects layout |
| `pad_top` | `3` | space above the plot area |
| `pad_bottom` | `3` | space below |
| `pad_right` | `None` | space right; `None` means `node_width_px + 3`, the minimum that fits the last column |
| `label_gutter_px` | `3` | space left, for labels. Only `"left"` mode needs more. See [Labels](#labels) |
| `preserve_column_pitch` | `True` | widen the figure to offset the gutter instead of narrowing the columns |
| `background_color` | `None` | `None` exports transparent |

### Nodes

| Key | Default | Meaning |
|---|---|---|
| `node_width_px` | `10` | rectangle width |
| `node_size_mode` | `"max"` | size a node by the larger (`"max"`) or smaller (`"min"`) of its inflow and outflow |
| `node_gap_px` | `4.5` | vertical gap between nodes in a column, honoured exactly |
| `node_edge_color` | `None` | outline colour; `None` means no outline |
| `node_edge_width_px` | `0.0` | outline width |
| `align_sinks_right` | `True` | push nodes with no outgoing links to the last column |

`node_gap_px` is exact: ask for 4.5 and the rendered gap measures 4.5 pixels,
whatever the data. That is less trivial than it sounds: the gaps change the
diagram's total height, which changes the scale the gaps are drawn at, so the
library solves for it rather than dividing once.

`node_size_mode="min"` can make a node shorter than the links attached to it,
which would need overlapping ribbons. That raises.

### Links

| Key | Default | Meaning |
|---|---|---|
| `link_inset_px` | `1.0` | gap between a node's edge and its ribbons |
| `link_alpha` | `0.5` | ribbon opacity |
| `control_point_split` | `(2/3, 1/3)` | where the Bézier control points sit along the span |
| `n_strips` | `48` | slices per ribbon used to fake a gradient |
| `link_flatten_alpha` | `False` | pre-blend against the background instead of using alpha |
| `link_stroke_width_px` | `0.0` | outline width on ribbons |

`control_point_split` shapes the curve. The two values are fractions of the
horizontal span, and note they **cross**: the first belongs to the start point and
sits *further* along than the second, which belongs to the end. That is what gives
the ribbon a flat approach at each end and a steep middle. `(0.5, 0.5)` gives the
more common gentler S-curve; `(1.0, 0.0)` is nearly a straight diagonal.

### Labels

| Key | Default | Meaning |
|---|---|---|
| `label_font_family` | `["DejaVu Sans"]` | family list, first available wins |
| `label_font_size_px` | `12` | size in pixels |
| `label_line_height_px` | `14.4` | minimum vertical distance between two labels in a column |
| `label_color` | `"#20282C"` | text colour |
| `label_padding_px` | `4` | gap between node and label |
| `label_border_width_px` | `1` | added to the label offset |
| `label_side_mode` | `"outside"` | `"outside"` points labels away from the plot middle; `"left"` puts them all left and needs a gutter |
| `min_label_height_px` | `8` | nodes shorter than this get no label |
| `label_collision_separation` | `True` | nudge apart labels still overlapping after the drop |
| `font_paths` | `[]` | font files to register before drawing |

### Export

| Key | Default | Meaning |
|---|---|---|
| `svg_fonttype` | `"none"` | `"none"` keeps SVG text as text; `"path"` converts glyphs to outlines |
| `pdf_fonttype` | `42` | `42` embeds TrueType so PDF text stays selectable |
| `ps_fonttype` | `42` | same for PostScript |
| `svg_hashsalt` | `"sankey_mpl"` | fixes SVG element ids so output is reproducible |

## The pixel contract

The figure is sized so that **one data unit = one point = one pixel**, with the
y-axis inverted so y grows downward. Everything follows from that:

- `label_font_size_px = 12` really is 12 pixels tall, at any dpi. There is no
  `72 / dpi` conversion anywhere in the library, and if you find yourself needing
  one, something has resized the figure.
- Width and line-width keys take pixel values directly.
- `device_pixel_ratio` is purely an export scale. At 1 a PNG comes out
  `width_px × height_px`; at 3 it is three times that in each direction, with an
  identical layout. Vector formats measure in points, so SVG and PDF always land
  at exactly `width_px × height_px`.

The one way to break this: passing `bbox_inches="tight"` or `pad_inches` when
saving. Both resize the figure box, after which the diagram is no longer the size
you configured. `save()` never passes them; don't add them.

## Labels

The only part that needs a decision from you, because sankey labels have nowhere
good to go. Default behaviour:

1. **Every label points away from the middle of the plot.** Columns in the left
   half get their label on the right of the node, columns in the right half on the
   left, so the outermost labels lean into the figure rather than off its edges.
   This mirrors the original library. It needs no gutter, and the cost is that
   interior labels sit over the ribbons leaving their own node.
2. **Nodes shorter than `min_label_height_px` get no label.** A thin node's label
   would collide with its neighbours and no label is better than two overlapping
   ones. Check `.labels_dropped` to see what was suppressed, and mention those
   values in a caption if they matter.
3. **Whatever still overlaps is nudged apart** to `label_line_height_px`, moving
   both labels of a colliding pair off their shared midpoint. Order is preserved,
   so labels never swap places relative to their nodes.

### The one collision the separation pass cannot fix

Step 3 works **within a column**. That is deliberate, but it leaves one gap, and it
is the gap the default rule creates: the column just left of the plot middle aims
its labels right, and the column just right of it aims them left, so both land in
the same space between the two columns. Those two labels are in different columns, so
the separation pass never compares them, and they can print on top of each other.

Nothing detects this for you. If your labels are long, either give the figure enough
width that both fit in the column pitch, or switch to `"left"` mode, where every
label points the same way and the pass sees every collision. A quick check:

```python
result = render_sankey(nodes, links, config)
for label in result.labels:
    width = text_width(label["text"], result.config)
    span = (
        (label["x"], label["x"] + width)
        if label["side"] == "right"
        else (label["x"] - width, label["x"])
    )
    print(label["text"], span, label["y"])
```

Two entries whose spans overlap at nearly the same `y` are drawn on top of each
other. The gallery in the repository README is sized by exactly this measurement.

### The alternative: keeping text off the ribbons

`label_side_mode="left"` puts every label to the left of its node instead, in the
gutter for column 0 and over the *incoming* ribbons for later columns. Interior
labels then sit in the gap between columns rather than on the ribbons leaving their
node, which reads better on a wide figure with long labels. Use it when legibility
matters more than horizontal space.

It is not a drop-in switch: it needs a gutter.

### Sizing the gutter

`label_gutter_px` becomes the left padding. Under the default it only has to be a
hairline, which is why it defaults to `3`. Under `"left"` mode column 0's labels
have to fit in it, and if they don't the library raises rather than letting text run
off the figure. Size it from your data:

```python
from sankey_mpl import render_sankey, text_width

widest = max(text_width(spec["label"]) for spec in first_column_nodes.values())
result = render_sankey(
    nodes, links, {"label_side_mode": "left", "label_gutter_px": widest + 10}
)
```

A gutter eats into the plot area, which shortens every ribbon and steepens its
curve. `preserve_column_pitch=True` (the default) compensates by widening the
figure, so a 900px figure with a 200px gutter comes out 1097px wide with the
column spacing a 900px figure would have had. Set it to `False` to keep the width
you asked for and accept narrower columns.

That widening is also the trap in raising the gutter without switching modes: under
the default nothing needs the room, so all you get is an empty left margin and a
figure wider than you asked for.

There is no "labels centred above nodes" mode. If that is what you need, suppress
labels entirely (`min_label_height_px` above your tallest node) and place text
yourself using `as_dict()["nodes"][key]["rect"]`.

### Fonts

The default family is `DejaVu Sans`, which ships with matplotlib and is therefore
always available. To use your own, register the file and name the family:

```python
render_sankey(
    nodes,
    links,
    {
        "font_paths": ["/path/to/MyFont-Regular.ttf"],
        "label_font_family": ["My Font", "DejaVu Sans"],
    },
)
```

matplotlib reads TrueType and OpenType, **not WOFF or WOFF2**. If your font is a
web font, get the `.ttf`/`.otf` from upstream rather than converting.

An unregistered family falls back silently, which matters here: the gutter check
and the collision pass both measure text, so the fallback changes the layout and
not just the appearance. Register fonts before rendering, and treat a font warning
as a real problem.

## Colour, gradients and alpha

Node colours come from `nodes`; the library has no palette of its own and never
picks colours for you. An uncoloured node is black.

Ribbons are drawn as a gradient from the source node's colour to the target's. A
matplotlib patch cannot carry a gradient fill, and the usual workaround, a
clipped image per ribbon, would rasterise them. Instead each ribbon is cut into
`n_strips` slices, each an exact piece of the same curve, each filled flat with the
colour the gradient would have there. Below about 24 slices the banding becomes
visible; 48 is invisible at print resolution.

Slices share edges, and each edge is antialiased on its own, so with real alpha the
shared boundaries show as very faint vertical hairlines. Two ways out, and neither
is universally better:

- **Leave `link_flatten_alpha=False`** (the default). Ribbons blend correctly where
  they cross, at the cost of those hairlines.
- **Set `link_flatten_alpha=True`** with an opaque `background_color`. Colours are
  pre-blended so the fills are opaque and the hairlines vanish, but crossing
  ribbons then paint over each other instead of blending.

For a light page with mostly non-crossing ribbons, flattening looks cleaner. For a
dense diagram where crossings carry meaning, keep the alpha.

## Embedding

`draw_sankey(ax, nodes, links, config)` puts the diagram in an axes you already
have, so it can be one panel of a bigger figure:

```python
from matplotlib.figure import Figure
from sankey_mpl import build_frame, draw_sankey

config = {
    "width_px": 720,  # the box you are drawing into
    "height_px": 360,
    "preserve_column_pitch": False,  # see below
    "label_side_mode": "left",  # a gutter is only useful in this mode
    "label_gutter_px": 180,
    "link_flatten_alpha": True,
    "background_color": "#FFFFFF",  # what is actually behind the diagram
}

# The page is in pixels too, so one axes rectangle is one box of the layout.
page = Figure(figsize=(792 / 72, 612 / 72), dpi=72)
ax = page.add_axes((36 / 792, 150 / 612, 720 / 792, 360 / 612))
drawing = draw_sankey(ax, nodes, links, config)
```

Four things behave differently from `render_sankey`, and all four bite silently
rather than raising:

- **Set `preserve_column_pitch=False` and `width_px` to your box width.** The
  default *widens* the diagram to offset the label gutter (a 900px request with
  the default 200px gutter comes out 1097px), which overflows the space you
  allotted. With it off, `frame.width == width_px` and the box is exact. If you
  want the widening, call `build_frame()` first and size the box from
  `frame.width` instead.
- **The axes limits are not yours to set.** `draw_sankey` sets them itself, to
  `xlim (0, frame.width)` and `ylim (frame.height, 0)`, because those limits *are*
  the [pixel contract](#the-pixel-contract): getting them wrong rescales the
  diagram instead of failing. Anything you set beforehand is overwritten.
- **The axes facecolor is left alone**, since an embedded diagram sits on a
  surface its host already painted. So `background_color` here does only its other
  job: telling `link_flatten_alpha=True` what to pre-blend the ribbons against. It
  still has to be set, and set to the colour genuinely behind the diagram (the
  card, not the page, if those differ), or the ribbons come out blended for a
  surface that isn't there.
- **The axes box must have the aspect the frame asks for.** One data unit is one
  pixel only if `frame.width × frame.height` pixels of figure are actually
  underneath it. Compute the axes rectangle from the same pixel numbers as the
  rest of your page and the contract holds; stretch the box and everything inside
  it stretches with it, `label_font_size_px` included.

Everything else is the same, `as_dict()` included, so a diagram embedded in a page
and the same diagram rendered standalone resolve to identical geometry.

## Export

```python
save(result, "diagram.svg")  # vector, text stays text
save(result, "diagram.pdf")  # vector, TrueType embedded, text selectable
save(result, "diagram.png")  # raster at device_pixel_ratio
```

Nothing in the output is rasterised, so SVG and PDF scale without softening and
their text can be selected, copied and searched.

**SVG fonts are a real choice.** The default `svg_fonttype="none"` writes
`font-family` and leaves the font to whatever opens the file: the text stays
selectable, but it needs that font installed or it will substitute. `"path"`
converts glyphs to outlines: identical appearance anywhere and fully
self-contained, at the cost of selectable text and a larger file. Choose `"none"`
when you control the rendering environment and `"path"` when you don't.

**PDF text needs `pdf_fonttype=42`,** which is the default here but not
matplotlib's. matplotlib defaults to Type 3, which renders correctly but cannot be
selected or searched, and some extractors get nothing out of it.

With `background_color=None` (the default) output is transparent, so the diagram
composites onto whatever page it lands on. Remember that alpha ribbons over a
transparent background take their tint from that page: a ribbon over white reads
lighter than the same ribbon over a dark surface. If you are targeting a dark
page, set `label_color` to something light: the default `#20282C` assumes a light
one.

## Reproducibility

The same input produces byte-identical output. This is not matplotlib's default
behaviour: SVG element ids derive from object identity and every format embeds a
timestamp, so `save()` fixes the id salt and drops the timestamps.

The guarantee holds **within one matplotlib version, not across versions.**
matplotlib changes its own output between releases. So:

- Comparing two renders in one process is a valid test, and a good one.
- Committing a golden `.svg` and diffing future runs against it will break on the
  next matplotlib upgrade. Pin the version if you need that, or compare resolved
  geometry from `as_dict()` instead, which is stable across matplotlib versions
  because the library computes it.

Comparing rendered *images* against another renderer is not worth attempting;
antialiasing differs between rasterisers and the diff never goes clean.

## Differences from chartjs-chart-sankey

Geometry matches the original given the same input, verified against golden data
generated by running it. These are the deliberate exceptions.

| | Original | Here | Why |
|---|---|---|---|
| Node gap | derived from the browser's backing-store height, so it changes with display density and dataset | `node_gap_px`, honoured exactly | the browser quantity has no meaning outside a browser |
| Labels | one rule, no collision handling, no clipping | same side rule, plus a drop rule and a separation pass | a static image has no tooltip to rescue an unreadable label |
| Node outline | 1px, in a palette colour auto-assigned by a Chart.js plugin | none | it was never a design decision upstream |
| Ribbon outline | 0.5px stroke in the gradient | none | not reproducible without rasterising |
| Cycles, backward links, disconnected graphs | handled by force-placing nodes or looping ribbons over the top of the canvas | raise | those outputs mislead more than they inform |
| Theme colours | read live from the DOM | passed in | there is no DOM |

Ribbons do **not** taper in either implementation: thickness comes from the source
side only, so a ribbon into a node whose inflow and outflow differ keeps its
source thickness the whole way.

## Errors

Every one of these is a refusal to draw something misleading.

| Message | Cause | Fix |
|---|---|---|
| `the graph contains a cycle` | links form a loop | break the cycle; this layout is for acyclic flows |
| `links must move forward between columns` | a link points leftward once columns are assigned, usually a subtle cycle | check the direction of the named link |
| `these nodes are not reachable...` | the graph has disconnected pieces | render each piece separately |
| `node X is shorter than the links attached to it` | `node_size_mode="min"` on unbalanced flow | use `"max"`, or balance the data |
| `a Npx gap repeated k times does not fit` | `node_gap_px` too large for the height and node count | reduce the gap or increase `height_px` |
| `label_gutter_px=N is too narrow` | column 0's widest label does not fit, only possible in `"left"` mode | widen the gutter using `text_width()`, or drop back to the default `"outside"` mode |
| `pad_right must be at least...` | right padding cannot fit the last column's rectangles | leave `pad_right=None` |
| `padding leaves no room to draw` | padding exceeds the figure | increase `width_px`/`height_px` |
| `unknown config keys` | a typo, or camelCase instead of snake_case | the message lists every valid key |
| `link_flatten_alpha needs an opaque background_color` | flattening with a transparent background | set `background_color`, or leave flattening off |

## Recipes

**A report figure on a light page**

```python
render_sankey(
    nodes,
    links,
    {
        "width_px": 1000,
        "height_px": 420,
        "label_side_mode": "left",
        "label_gutter_px": 180,
        "label_color": "#20282C",
        "link_flatten_alpha": True,
        "background_color": "#FFFFFF",
    },
)
```

**A dark-theme web asset**

```python
render_sankey(
    nodes,
    links,
    {
        "label_color": "#EEF2F4",
        "background_color": "#12181C",
        "link_flatten_alpha": True,
    },
)
```

**Print PDF, self-contained**

```python
config = {"device_pixel_ratio": 1, "svg_fonttype": "path"}
save(render_sankey(nodes, links, config), "figure.pdf", config)
```

**Labels off the ribbons, on a wide figure**

```python
render_sankey(
    nodes,
    links,
    {
        "width_px": 1400,
        "label_side_mode": "left",
        "label_gutter_px": text_width("your longest first-column label") + 20,
    },
)
```

**Inspect the layout without drawing**

```python
from sankey_mpl import compute_layout

layout = compute_layout(nodes, links, gap_px=4.5, plot_height=354)
for key, node in layout.nodes.items():
    print(key, "column", node.column, "top", node.y, "height", node.size)
```
