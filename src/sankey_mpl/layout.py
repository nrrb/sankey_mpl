"""Sankey layout: columns, vertical placement, node gaps, link stacking.

Pure Python — no matplotlib, no numpy. Everything here works in *flow units*
(whatever unit the caller's ``flow`` values are in) and column indices. Turning
those into pixels is ``geometry.py``'s job.

The algorithm is a port of ``chartjs-chart-sankey``, and it is worth knowing that
it is not the textbook sankey layout. Two things in particular surprise people:

* Vertical order inside a column is not the result of a sort. It emerges from a
  traversal that follows links outward from a seed node, and a later sweep only
  fixes overlaps. Two nodes can therefore sit in an order that no simple key
  would produce.
* Ties are broken by a four-step chain — subtree size, then degree, then flow,
  then *input order*. Data with distinct flows is therefore insensitive to the
  order links are supplied in, but genuinely equal flows are not, so that order
  is part of the input rather than an incidental detail.

Both are faithful to the original, and both are the reason this module mirrors
the original's sequence of in-place sorts rather than deriving one combined
ordering key.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

__all__ = [
    "Link",
    "Node",
    "SankeyLayout",
    "compute_layout",
]

# The nudge that keeps sibling subtrees from starting at exactly the same
# coordinate. It is far below one flow unit in any realistic dataset, but it must
# survive: rounding it away changes which of two tied nodes ends up on top.
_EPSILON = 1e-6


class Link:
    """One link as held on a node's ``incoming`` / ``outgoing`` list."""

    __slots__ = ("key", "index", "flow", "node", "offset")

    def __init__(self, key: str, index: int, flow: float, node: Node) -> None:
        self.key = key
        self.index = index
        self.flow = flow
        self.node = node
        # Distance from the owning node's top edge to this link's top edge, in
        # flow units. Filled in by _stack_links.
        self.offset = 0.0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Link {self.key} flow={self.flow} offset={self.offset}>"


class Node:
    __slots__ = (
        "key",
        "label",
        "color",
        "inflow",
        "outflow",
        "size",
        "column",
        "_column_set",
        "y",
        "_y_set",
        "y_unpadded",
        "gap_slots",
        "outgoing",
        "incoming",
    )

    def __init__(self, key: str) -> None:
        self.key = key
        self.label: str | None = None
        self.color: str | None = None
        self.inflow = 0.0
        self.outflow = 0.0
        #: Height of the node in flow units.
        self.size = 0.0
        #: Column index, assigned by levelling. 0 until then, which is what
        #: ``_column_set`` distinguishes: the public contract is that this is a
        #: real index by the time a layout is returned, so it is typed ``int``
        #: rather than optional and callers need no narrowing.
        self.column: int = 0
        self._column_set = False
        #: Top edge in flow units, after gaps have been applied. 0.0 until the
        #: traversal reaches this node; ``_y_set`` is what tells the two apart,
        #: and an unreached node is what the disconnected-graph guard detects.
        self.y: float = 0.0
        self._y_set = False
        #: Top edge before gaps. Kept because the gap solve needs both.
        self.y_unpadded = 0.0
        #: How many gap quanta sit above this node. See _count_gap_slots.
        self.gap_slots = 0
        self.outgoing: list[Link] = []
        self.incoming: list[Link] = []

    @property
    def extent(self) -> float:
        """The height the node occupies when measuring total diagram height.

        This is ``max(inflow, outflow)`` rather than ``size``. The two agree for
        ``node_size_mode="max"``, which is the only mode that reaches here.
        """
        return max(self.inflow, self.outflow)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Node {self.key!r} column={self.column} y={self.y} size={self.size}>"


class SankeyLayout:
    """Resolved layout in flow units. Consumed by ``geometry.py``."""

    __slots__ = (
        "nodes",
        "links",
        "max_column",
        "total_height",
        "total_height_unpadded",
        "gap_units",
        "gap_slots_at_max",
    )

    def __init__(
        self,
        nodes: dict[str, Node],
        links: Sequence[Mapping[str, Any]],
        max_column: int,
        total_height: float,
        total_height_unpadded: float,
        gap_units: float,
        gap_slots_at_max: int,
    ) -> None:
        self.nodes = nodes
        self.links = links
        #: Highest column index in use; there are ``max_column + 1`` columns.
        self.max_column = max_column
        #: Diagram height in flow units, gaps included. The vertical scale's max.
        self.total_height = total_height
        #: The same before gaps were added.
        self.total_height_unpadded = total_height_unpadded
        #: One gap, in flow units.
        self.gap_units = gap_units
        #: Gap count above the node that sets ``total_height``.
        self.gap_slots_at_max = gap_slots_at_max

    @property
    def node_list(self) -> list[Node]:
        return list(self.nodes.values())

    def link_offset(self, node: Node, side: str, key: str, index: int) -> float:
        """Where a specific link attaches, measured from ``node``'s top edge."""
        refs = node.outgoing if side == "outgoing" else node.incoming
        for ref in refs:
            if ref.key == key and ref.index == index:
                return ref.offset
        return 0.0


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #


def _size_of(node: Node, mode: str) -> float:
    # The fallbacks let a pure source (no inflow) be sized by its outflow and a
    # pure sink (no outflow) by its inflow.
    a = node.inflow or node.outflow
    b = node.outflow or node.inflow
    return max(a, b) if mode == "max" else min(a, b)


def _build_nodes(links: Sequence[Mapping[str, Any]], size_mode: str) -> dict[str, Node]:
    """Build the node map, then pre-sort every link list.

    Insertion order into the returned dict is deliberate: a node is registered
    when its first link is attached, and that order is the last tie-break in
    several later comparisons. It reproduces the original's Map ordering.
    """
    nodes: dict[str, Node] = {}
    pool: dict[str, Node] = {}

    def obtain(key: str) -> Node:
        node = pool.get(key)
        if node is None:
            node = Node(key)
            pool[key] = node
        return node

    for index, link in enumerate(links):
        try:
            from_key, to_key, flow = link["from"], link["to"], float(link["flow"])
        except KeyError as exc:  # pragma: no cover - input validation
            raise ValueError(
                f"link {index} is missing {exc.args[0]!r}; each link needs "
                "'from', 'to' and 'flow'"
            ) from None
        if flow < 0:
            raise ValueError(f"link {index} ({from_key} -> {to_key}) has negative flow")

        from_node = obtain(from_key)
        to_node = from_node if from_key == to_key else obtain(to_key)

        from_node.outflow += flow
        from_node.outgoing.append(Link(to_key, index, flow, to_node))
        if len(from_node.outgoing) == 1:
            nodes.setdefault(from_key, from_node)

        to_node.inflow += flow
        to_node.incoming.append(Link(from_key, index, flow, from_node))
        if len(to_node.incoming) == 1:
            nodes.setdefault(to_key, to_node)

    # Flow descending, then input order. Every sort after this one is stable, so
    # this survives as the residual tie-break throughout.
    for node in nodes.values():
        node.incoming.sort(key=lambda ref: (-ref.flow, ref.index))
        node.outgoing.sort(key=lambda ref: (-ref.flow, ref.index))
        node.size = _size_of(node, size_mode)
    return nodes


# --------------------------------------------------------------------------- #
# Columns
# --------------------------------------------------------------------------- #


def _reachable_forward(start: Iterable[Node]) -> set[str]:
    seen: set[str] = set()
    stack = list(start)
    while stack:
        node = stack.pop()
        if node.key in seen:
            continue
        seen.add(node.key)
        stack.extend(ref.node for ref in node.outgoing)
    return seen


def _first_column(links: Sequence[Mapping[str, Any]], nodes: Sequence[Node]) -> list[str]:
    """Column 0 is every node with no incoming link.

    The loop afterwards only matters for a disconnected component that has no
    source at all, where it elects that component's first-seen node as an entry
    point so the levelling below can make progress.
    """
    sources = [node for node in nodes if not node.incoming]
    column = [node.key for node in sources]
    referenced = _reachable_forward(sources)
    for link in links:
        if link["from"] not in referenced and link["to"] not in referenced:
            column.append(link["from"])
            referenced.add(link["from"])
        referenced.add(link["to"])
    return column


def _following_column(
    links_without_self_loops: Sequence[Mapping[str, Any]],
    remaining: Mapping[str, Any],
) -> list[str]:
    """A node may advance once nothing still-unplaced flows into it.

    Kahn-style levelling. The original breaks a deadlock by force-placing an
    arbitrary node; this port refuses instead, because a cycle means the caller's
    data is not the acyclic flow this layout assumes.
    """
    still_targeted = {
        link["to"] for link in links_without_self_loops if link["from"] in remaining
    }
    placeable = [key for key in remaining if key not in still_targeted]
    if not placeable:
        raise ValueError(
            "the graph contains a cycle, which this layout cannot place: none of "
            f"{sorted(remaining)} can advance to the next column"
        )
    return placeable


def _assign_columns(
    nodes: Mapping[str, Node],
    links: Sequence[Mapping[str, Any]],
    align_sinks_right: bool,
) -> int:
    links_without_self_loops = [link for link in links if link["from"] != link["to"]]
    node_list = list(nodes.values())
    remaining = dict.fromkeys(nodes)  # insertion-ordered set
    column = 0
    while remaining:
        keys = (
            _first_column(links, node_list)
            if column == 0
            else _following_column(links_without_self_loops, remaining)
        )
        for key in keys:
            node = nodes.get(key)
            if node is not None and not node._column_set:
                node.column = column
                node._column_set = True
            remaining.pop(key, None)
        if remaining:
            column += 1

    max_column = max(node.column for node in node_list)

    if align_sinks_right:
        # Every node that is never a link source moves to the last column, so
        # short paths still end flush with long ones. max_column is measured
        # before this pass and is not changed by it.
        link_sources = {link["from"] for link in links}
        for node in node_list:
            if node.key not in link_sources:
                node.column = max_column
                node._column_set = True
    return max_column


def _require_forward_links(nodes: Mapping[str, Node]) -> None:
    """Every link must move strictly rightward.

    The original handles backward links by looping the ribbon over the top of the
    canvas. That path is not implemented here, so the condition that would reach
    it is rejected up front instead of rendering something misleading.
    """
    for node in nodes.values():
        for ref in node.outgoing:
            if ref.node.column <= node.column:
                raise ValueError(
                    "links must move forward between columns, but "
                    f"{node.key!r} (column {node.column}) links to "
                    f"{ref.key!r} (column {ref.node.column})"
                )


# --------------------------------------------------------------------------- #
# Vertical placement
# --------------------------------------------------------------------------- #


def _seed_node(node_list: Sequence[Node], max_column: int) -> Node:
    """The node the traversal starts from: the tallest, tie-broken by position."""
    tallest = max(node.size for node in node_list)
    candidates = [node for node in node_list if node.size == tallest]
    if len(candidates) == 1:
        return candidates[0]
    candidates.sort(key=lambda node: node.column)
    if candidates[0].column == 0:
        return candidates[0]
    if candidates[-1].column == max_column:
        return candidates[-1]
    return candidates[len(candidates) // 2]


def _subtree_size(refs: Sequence[Link], side: str, seen: set[int]) -> int:
    """Total number of links below these, counting each node once."""
    count = 0
    for ref in refs:
        node = ref.node
        if id(node) in seen:
            continue
        seen.add(id(node))
        below = getattr(node, side)
        count += len(below) + _subtree_size(below, side, seen)
    return count


def _sort_by_subtree(refs: list[Link], side: str) -> None:
    """Thinner subtrees first, then lower degree.

    A stable sort, so links whose subtrees are the same shape keep the
    flow-descending / input-order sequence established at build time. That chain
    — subtree size, then degree, then flow, then input order — is the whole
    tie-break rule for vertical placement.
    """
    refs.sort(
        key=lambda ref: (
            _subtree_size(getattr(ref.node, side), side, set()),
            len(getattr(ref.node, side)),
        )
    )


def _walk_incoming(node: Node, y: float) -> float:
    if not node.incoming:
        return y
    _sort_by_subtree(node.incoming, "incoming")
    for ref in node.incoming:
        upstream = ref.node
        if not upstream._y_set:
            upstream.y = y
            upstream._y_set = True
            _walk_incoming(upstream, y + _EPSILON if y else 0.0)
        y = max(upstream.y + upstream.outflow, y)
    return node.y + node.size


def _walk_outgoing(node: Node, y: float) -> float:
    if not node.outgoing:
        return y
    _sort_by_subtree(node.outgoing, "outgoing")
    for ref in node.outgoing:
        downstream = ref.node
        if not downstream._y_set:
            downstream.y = y
            downstream._y_set = True
            _walk_outgoing(downstream, y + _EPSILON if y else 0.0)
        y = max(downstream.y + downstream.extent, y)
    return node.y + node.size


def _resolve_overlaps(node_list: Sequence[Node], max_column: int) -> None:
    """Per column, push any overlapping node down.

    This is the only guarantee that two nodes in a column do not overlap. It
    pushes down only: gaps the traversal left behind are preserved, which is why
    a column with less total flow ends higher up rather than being stretched.
    """
    for column in range(max_column + 1):
        members = sorted(
            (node for node in node_list if node.column == column),
            key=lambda node: node.y,
        )
        floor = 0.0
        for node in members:
            if node.y < floor:
                node.y = floor
            floor = node.y + node.size


def _place_vertically(node_list: Sequence[Node], max_column: int) -> None:
    seed = _seed_node(node_list, max_column)
    seed.y = 0.0
    seed._y_set = True
    _walk_incoming(seed, 0.0)
    _walk_outgoing(seed, 0.0)
    # The original has a recovery pass for nodes the traversal never reached.
    # It cannot trigger for a graph whose nodes are all reachable from the seed,
    # which is every connected forward graph, so this refuses instead.
    stranded = [node.key for node in node_list if not node._y_set]
    if stranded:
        raise ValueError(
            "these nodes are not reachable from the largest node and cannot be "
            f"placed: {sorted(stranded)}. Disconnected graphs are unsupported."
        )
    _resolve_overlaps(node_list, max_column)


# --------------------------------------------------------------------------- #
# Node gaps
# --------------------------------------------------------------------------- #


def _count_gap_slots(node_list: list[Node]) -> None:
    """Record how many gap quanta sit above each node, without moving anything.

    A node's own column contributes one slot per node already placed above it.
    Earlier columns can raise that count: if an earlier column has more nodes
    above this node's height than this column does, the extra rows are carried
    over. That carry-over is what keeps a link roughly horizontal instead of
    letting it drift downward as gaps accumulate to the right.

    Counting is deliberately separate from applying, because the count depends
    only on pre-gap positions. That independence is what makes it possible to
    solve for a gap size that renders to an exact pixel height.
    """
    column_slot: dict[int, int] = {}
    grid: list[list[float]] = []

    def slot_for(column: int) -> int:
        if column not in column_slot:
            column_slot[column] = len(grid)
            grid.append([])
        return column_slot[column]

    node_list.sort(key=lambda node: (node.column, node.y, node.size))
    for node in node_list:
        node.y_unpadded = node.y
        index = slot_for(node.column)
        column = grid[index]
        y = node.y_unpadded
        if not y:
            # A node flush with the top of the diagram gets no gap above it.
            node.gap_slots = 0
            continue
        column.append(y)
        slots = len(column)
        if node.inflow:
            for earlier in range(index):
                other = grid[earlier]
                for row, value in enumerate(other):
                    if value > y:
                        break
                    slots = max(row + 1, slots)
                while len(column) < slots:
                    column.append(y)
        node.gap_slots = slots


def _height_at(node_list: Sequence[Node], gap: float) -> tuple[float, Node]:
    """Total diagram height for a hypothetical gap size, and the node setting it."""
    tallest = max(
        node_list, key=lambda node: node.y_unpadded + node.gap_slots * gap + node.extent
    )
    return tallest.y_unpadded + tallest.gap_slots * gap + tallest.extent, tallest


def _solve_gap(node_list: Sequence[Node], gap_px: float, plot_height: float) -> float:
    """Find the gap, in flow units, that renders as exactly ``gap_px`` pixels.

    The obvious formula — pixels divided by the provisional scale — is wrong, and
    wrong in a way that is easy to miss. It converts using the scale *before*
    gaps are added, but the gap is drawn against the scale *after*, which is
    smaller because the gaps themselves made the diagram taller. The result comes
    out short by a factor that grows with the number of gaps, so it is least
    accurate on exactly the dense diagrams where gap size is most visible.

    Solving properly: let ``A`` be the pre-gap extent of the node that ends up
    setting the total height and ``k`` its gap-slot count. Requiring

        gap_px = gap * plot_height / (A + k * gap)

    rearranges to

        gap = gap_px * A / (plot_height - gap_px * k)

    Which node sets the height can change once gaps are applied, so this starts
    from the pre-gap tallest node and re-solves until the winner stops moving.
    Total height is a maximum of straight lines in ``gap``, so each step moves to
    the line that is actually on top and the search settles immediately.
    """
    if gap_px == 0:
        return 0.0
    _, winner = _height_at(node_list, 0.0)
    for _ in range(8):
        slots = winner.gap_slots
        if gap_px * slots >= plot_height:
            raise ValueError(
                f"a {gap_px}px gap repeated {slots} times does not fit in a "
                f"{plot_height}px plot area; reduce the gap or increase the height"
            )
        gap = (
            gap_px * (winner.y_unpadded + winner.extent) / (plot_height - gap_px * slots)
        )
        _, candidate = _height_at(node_list, gap)
        if candidate.gap_slots == slots:
            total, _ = _height_at(node_list, gap)
            rendered = gap * plot_height / total
            if abs(rendered - gap_px) >= 1e-9:  # pragma: no cover - guards the maths
                raise AssertionError(
                    f"solved gap renders as {rendered}px, not the requested {gap_px}px"
                )
            return gap
        winner = candidate
    raise AssertionError(  # pragma: no cover - guards the maths
        "gap solve failed to settle on which node sets the diagram height"
    )


def _apply_gaps(node_list: Sequence[Node], gap: float) -> float:
    total = 0.0
    for node in node_list:
        node.y = node.y_unpadded + node.gap_slots * gap
        total = max(total, node.y + node.extent)
    return total


# --------------------------------------------------------------------------- #
# Link stacking
# --------------------------------------------------------------------------- #


def _stack_links(node_list: Sequence[Node]) -> None:
    """Order the links on each node and give each one an offset.

    Links are ordered by the vertical centre of the band they connect to at the
    *other* end, which is what keeps ribbons from crossing unnecessarily. Offsets
    then accumulate down the node's edge in that order.
    """
    for node in node_list:
        if node.size < node.inflow or node.size < node.outflow:
            # The original squeezes overlapping ribbons onto a node too short to
            # hold them. Unreachable while size is max(inflow, outflow), which is
            # never smaller than either.
            raise ValueError(
                f"node {node.key!r} is shorter than the links attached to it, "
                "which would require overlapping ribbons"
            )

        node.incoming.sort(key=lambda ref: ref.node.y + ref.node.outflow / 2.0)
        offset = 0.0
        for ref in node.incoming:
            ref.offset = offset
            offset += ref.flow

        node.outgoing.sort(key=lambda ref: ref.node.y + ref.node.inflow / 2.0)
        offset = 0.0
        for ref in node.outgoing:
            ref.offset = offset
            offset += ref.flow


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def compute_layout(
    nodes: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    *,
    gap_px: float,
    plot_height: float,
    size_mode: str = "max",
    align_sinks_right: bool = True,
) -> SankeyLayout:
    """Resolve a sankey layout in flow units.

    ``nodes`` supplies optional ``label`` and ``color`` per key; keys absent from
    ``links`` are ignored. ``links`` is a sequence of ``{"from", "to", "flow"}``
    and its order is significant — see the module docstring.

    ``gap_px`` and ``plot_height`` are both in pixels, and are the only pixel
    values this module touches: the gap has to be solved against the final
    vertical scale, so it cannot be deferred to the geometry layer.
    """
    if not links:
        raise ValueError("links is empty; there is nothing to lay out")
    if size_mode not in ("max", "min"):
        raise ValueError(f"size_mode must be 'max' or 'min', not {size_mode!r}")
    if plot_height <= 0:
        raise ValueError(f"plot_height must be positive, not {plot_height}")

    graph = _build_nodes(links, size_mode)
    for key, node in graph.items():
        spec = nodes.get(key, {})
        node.label = spec.get("label")
        node.color = spec.get("color")

    max_column = _assign_columns(graph, links, align_sinks_right)
    _require_forward_links(graph)

    node_list = list(graph.values())
    _place_vertically(node_list, max_column)
    _count_gap_slots(node_list)
    unpadded, _ = _height_at(node_list, 0.0)
    gap_units = _solve_gap(node_list, gap_px, plot_height)
    total = _apply_gaps(node_list, gap_units)
    _, winner = _height_at(node_list, gap_units)
    _stack_links(node_list)

    # _count_gap_slots reorders node_list in place; rebuild the map so iteration
    # order stays the caller-visible one.
    ordered = {node.key: node for node in graph.values()}
    return SankeyLayout(
        nodes=ordered,
        links=links,
        max_column=max_column,
        total_height=total,
        total_height_unpadded=unpadded,
        gap_units=gap_units,
        gap_slots_at_max=winner.gap_slots,
    )
