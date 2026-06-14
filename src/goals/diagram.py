"""Generate clean diagrams from goals' structured models.

Two formats:

* **Mermaid** — zero-dependency flowchart text that renders in GitHub, the
  dashboard, and most markdown viewers.
* **Excalidraw** — a valid ``.excalidraw`` JSON document with a deterministic
  layered layout, following the format rules that make *raw* Excalidraw JSON
  render correctly (technique adapted from the community ``excalidraw`` skill):

  - rectangles only — diamond arrow-binding is broken in raw JSON;
  - every labeled shape is a rectangle **plus** a separate bound ``text`` element
    with a ``containerId`` — the ``label`` property does not work in raw JSON;
  - elbow arrows (``roughness: 0``, ``roundness: null``, ``elbowed: true``) for
    clean 90-degree corners;
  - arrows attach at shape **edge** coordinates, not centers.

Generating from goals' own structured data (architecture nodes/edges, loop
phases) makes the output deterministic and testable, unlike freehand code
analysis.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from goals.loop_builder import LoopDesign
from goals.models import GoalArchitectureMap

# stroke / background per node status.
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    "built": ("#2f9e44", "#ebfbee"),
    "in_progress": ("#1971c2", "#e7f5ff"),
    "planned": ("#868e96", "#f1f3f5"),
    "blocked": ("#e03131", "#fff5f5"),
    "deferred": ("#e8590c", "#fff4e6"),
    "removed": ("#adb5bd", "#f8f9fa"),
}
_DEFAULT_STATUS = "planned"

# Excalidraw layout constants.
_BOX_W = 220
_BOX_H = 80
_GAP_X = 140
_GAP_Y = 40

_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


@dataclass
class _Node:
    id: str
    label: str
    status: str


@dataclass
class _Edge:
    src: str
    dst: str
    label: str = ""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def render_architecture(amap: GoalArchitectureMap, *, fmt: str = "mermaid") -> str:
    nodes = [_Node(n.node_id, n.label, n.status) for n in amap.nodes]
    ids = {n.id for n in nodes}
    edges = [_Edge(e.from_node, e.to_node, e.relation) for e in amap.edges if e.from_node in ids and e.to_node in ids]
    return _render(nodes, edges, fmt=fmt, title=amap.title)


def render_loop(design: LoopDesign, *, fmt: str = "mermaid") -> str:
    nodes = [_Node(p.phase_id, f"{p.phase_id}: {p.title}", _DEFAULT_STATUS) for p in design.phases]
    edges = [
        _Edge(design.phases[i].phase_id, design.phases[i + 1].phase_id)
        for i in range(len(design.phases) - 1)
    ]
    return _render(nodes, edges, fmt=fmt, title=design.objective or "Loop")


def _render(nodes: list[_Node], edges: list[_Edge], *, fmt: str, title: str) -> str:
    if fmt == "mermaid":
        return _to_mermaid(nodes, edges)
    if fmt == "excalidraw":
        return json.dumps(_to_excalidraw(nodes, edges), indent=2) + "\n"
    raise ValueError(f"Unknown diagram format: {fmt}")


# --------------------------------------------------------------------------- #
# Mermaid
# --------------------------------------------------------------------------- #
def _to_mermaid(nodes: list[_Node], edges: list[_Edge]) -> str:
    lines = ["flowchart TD"]
    for node in nodes:
        lines.append(f'    {_safe_id(node.id)}["{_mermaid_text(node.label)}"]:::{node.status}')
    for edge in edges:
        rel = _mermaid_text(edge.label.replace("_", " ")) if edge.label else ""
        arrow = f"-->|{rel}|" if rel else "-->"
        lines.append(f"    {_safe_id(edge.src)} {arrow} {_safe_id(edge.dst)}")
    used = {n.status for n in nodes}
    for status in sorted(used):
        stroke, bg = _STATUS_STYLE.get(status, _STATUS_STYLE[_DEFAULT_STATUS])
        lines.append(f"    classDef {status} fill:{bg},stroke:{stroke},color:#1d2330;")
    return "\n".join(lines) + "\n"


def _safe_id(raw: str) -> str:
    cleaned = _ID_SAFE.sub("_", raw)
    return cleaned if cleaned and not cleaned[0].isdigit() else f"n_{cleaned}"


def _mermaid_text(text: str) -> str:
    # Quotes and brackets break Mermaid node labels; entity-escape them.
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
    )


# --------------------------------------------------------------------------- #
# Excalidraw
# --------------------------------------------------------------------------- #
def _to_excalidraw(nodes: list[_Node], edges: list[_Edge]) -> dict:
    positions = _layered_positions(nodes, edges)
    bound: dict[str, list[dict[str, str]]] = {n.id: [] for n in nodes}

    # Pre-register bound text + arrows on their owner rectangles.
    arrows: list[tuple[str, _Edge]] = []
    for index, edge in enumerate(edges):
        if edge.src in bound and edge.dst in bound:
            arrow_id = f"arrow-{index}-{_safe_id(edge.src)}-{_safe_id(edge.dst)}"
            arrows.append((arrow_id, edge))
            bound[edge.src].append({"type": "arrow", "id": arrow_id})
            bound[edge.dst].append({"type": "arrow", "id": arrow_id})

    elements: list[dict] = []
    seed = 1
    for node in nodes:
        x, y = positions[node.id]
        rect_id = f"rect-{_safe_id(node.id)}"
        text_id = f"text-{_safe_id(node.id)}"
        stroke, bg = _STATUS_STYLE.get(node.status, _STATUS_STYLE[_DEFAULT_STATUS])
        node_bound = [{"type": "text", "id": text_id}, *bound[node.id]]
        elements.append(_rect(rect_id, x, y, stroke, bg, node_bound, seed))
        elements.append(_text(text_id, node.label, x, y, rect_id, seed + 1))
        seed += 2

    rect_of = {node.id: (f"rect-{_safe_id(node.id)}", positions[node.id]) for node in nodes}
    for arrow_id, edge in arrows:
        src_rect, (sx, sy) = rect_of[edge.src]
        dst_rect, (dx, dy) = rect_of[edge.dst]
        elements.append(_arrow(arrow_id, src_rect, dst_rect, sx, sy, dx, dy, edge.label, seed))
        seed += 1

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "goals",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }


def _layered_positions(nodes: list[_Node], edges: list[_Edge]) -> dict[str, tuple[int, int]]:
    """Assign (x, y) per node via longest-path layering (left to right).

    Falls back to insertion order as the layer when the graph has a cycle, so
    layout never loops or crashes.
    """
    ids = [n.id for n in nodes]
    incoming: dict[str, list[str]] = {nid: [] for nid in ids}
    for edge in edges:
        if edge.src in incoming and edge.dst in incoming:
            incoming[edge.dst].append(edge.src)

    layer: dict[str, int] = {}

    def depth(nid: str, stack: frozenset[str]) -> int:
        if nid in layer:
            return layer[nid]
        if nid in stack or not incoming[nid]:
            layer[nid] = 0 if not incoming[nid] else ids.index(nid)
            return layer[nid]
        value = 1 + max(depth(src, stack | {nid}) for src in incoming[nid])
        layer[nid] = value
        return value

    for nid in ids:
        depth(nid, frozenset())

    rows: dict[int, int] = {}
    positions: dict[str, tuple[int, int]] = {}
    for nid in ids:
        col = layer[nid]
        row = rows.get(col, 0)
        rows[col] = row + 1
        positions[nid] = (col * (_BOX_W + _GAP_X), row * (_BOX_H + _GAP_Y))
    return positions


def _base(element_id: str, seed: int) -> dict:
    return {
        "id": element_id,
        "angle": 0,
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "seed": seed,
        "version": 1,
        "versionNonce": seed,
        "isDeleted": False,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def _rect(
    rect_id: str, x: int, y: int, stroke: str, bg: str, bound: list[dict], seed: int
) -> dict:
    return {
        **_base(rect_id, seed),
        "type": "rectangle",
        "x": x,
        "y": y,
        "width": _BOX_W,
        "height": _BOX_H,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": "solid",
        "roundness": {"type": 3},
        "boundElements": bound,
    }


def _text(text_id: str, label: str, x: int, y: int, container: str, seed: int) -> dict:
    return {
        **_base(text_id, seed),
        "type": "text",
        "x": x + 10,
        "y": y + _BOX_H // 2 - 12,
        "width": _BOX_W - 20,
        "height": 24,
        "strokeColor": "#1d2330",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "roundness": None,
        "text": label,
        "originalText": label,
        "fontSize": 16,
        "fontFamily": 1,
        "textAlign": "center",
        "verticalAlign": "middle",
        "containerId": container,
        "lineHeight": 1.25,
        "boundElements": [],
    }


def _arrow(
    arrow_id: str,
    src_rect: str,
    dst_rect: str,
    sx: int,
    sy: int,
    dx: int,
    dy: int,
    label: str,
    seed: int,
) -> dict:
    # Attach at shape EDGES: source right-middle -> target left-middle.
    start_x = sx + _BOX_W
    start_y = sy + _BOX_H // 2
    end_x = dx
    end_y = dy + _BOX_H // 2
    return {
        **_base(arrow_id, seed),
        "type": "arrow",
        "x": start_x,
        "y": start_y,
        "width": abs(end_x - start_x),
        "height": abs(end_y - start_y),
        "strokeColor": "#495057",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "roundness": None,
        "elbowed": True,
        "points": [[0, 0], [end_x - start_x, end_y - start_y]],
        "lastCommittedPoint": None,
        "startBinding": {"elementId": src_rect, "focus": 0, "gap": 4},
        "endBinding": {"elementId": dst_rect, "focus": 0, "gap": 4},
        "startArrowhead": None,
        "endArrowhead": "arrow",
        "boundElements": [],
    }
