import json

from goals.diagram import render_architecture, render_loop
from goals.loop_builder import LoopDesign, LoopPhase
from goals.models import ArchitectureEdge, ArchitectureNode, GoalArchitectureMap


def _map() -> GoalArchitectureMap:
    return GoalArchitectureMap(
        title="Demo",
        overview="o",
        nodes=[
            ArchitectureNode(node_id="api", label="API layer", plain_summary="x", status="built"),
            ArchitectureNode(
                node_id="db", label="Database", plain_summary="x", status="planned"
            ),
            ArchitectureNode(
                node_id="ui", label='UI "home"', plain_summary="x", status="blocked"
            ),
        ],
        edges=[
            ArchitectureEdge(from_node="ui", to_node="api", relation="calls"),
            ArchitectureEdge(from_node="api", to_node="db", relation="reads_from"),
        ],
    )


def _loop() -> LoopDesign:
    return LoopDesign(
        objective="Build it",
        phases=[
            LoopPhase(phase_id="P1", title="Plan"),
            LoopPhase(phase_id="P2", title="Build"),
            LoopPhase(phase_id="P3", title="Verify"),
        ],
    )


# --- Mermaid --------------------------------------------------------------- #
def test_architecture_mermaid_structure() -> None:
    out = render_architecture(_map(), fmt="mermaid")
    assert out.startswith("flowchart TD")
    assert "api[" in out and "db[" in out
    assert "ui -->|calls| api" in out
    assert "api -->|reads from| db" in out
    # status classes are emitted and assigned
    assert "classDef built" in out and ":::built" in out


def test_mermaid_escapes_quotes_in_labels() -> None:
    out = render_architecture(_map(), fmt="mermaid")
    assert '"home"' not in out  # raw quotes would break the node label
    assert "&quot;" in out


def test_loop_mermaid_is_sequential() -> None:
    out = render_loop(_loop(), fmt="mermaid")
    assert "P1 --> P2" in out
    assert "P2 --> P3" in out


# --- Excalidraw ------------------------------------------------------------ #
def test_excalidraw_is_valid_document() -> None:
    doc = json.loads(render_architecture(_map(), fmt="excalidraw"))
    assert doc["type"] == "excalidraw"
    assert doc["version"] == 2
    assert isinstance(doc["elements"], list) and doc["elements"]


def test_excalidraw_no_diamonds() -> None:
    doc = json.loads(render_architecture(_map(), fmt="excalidraw"))
    assert all(e["type"] != "diamond" for e in doc["elements"])


def test_excalidraw_every_rectangle_has_a_bound_text_element() -> None:
    doc = json.loads(render_architecture(_map(), fmt="excalidraw"))
    elements = {e["id"]: e for e in doc["elements"]}
    rects = [e for e in doc["elements"] if e["type"] == "rectangle"]
    assert len(rects) == 3
    for rect in rects:
        text_refs = [b for b in rect["boundElements"] if b["type"] == "text"]
        assert len(text_refs) == 1
        text_id = text_refs[0]["id"]
        assert text_id in elements
        text = elements[text_id]
        assert text["type"] == "text"
        assert text["containerId"] == rect["id"]  # the back-reference matches


def test_excalidraw_arrows_are_elbowed_and_bind_existing_rects() -> None:
    doc = json.loads(render_architecture(_map(), fmt="excalidraw"))
    ids = {e["id"] for e in doc["elements"]}
    arrows = [e for e in doc["elements"] if e["type"] == "arrow"]
    assert len(arrows) == 2
    for arrow in arrows:
        assert arrow["elbowed"] is True
        assert arrow["roundness"] is None
        assert arrow["roughness"] == 0
        assert arrow["startBinding"]["elementId"] in ids
        assert arrow["endBinding"]["elementId"] in ids


def test_excalidraw_is_deterministic() -> None:
    a = render_architecture(_map(), fmt="excalidraw")
    b = render_architecture(_map(), fmt="excalidraw")
    assert a == b


def test_empty_map_does_not_crash() -> None:
    empty = GoalArchitectureMap(title="t", overview="o", nodes=[], edges=[])
    assert "flowchart TD" in render_architecture(empty, fmt="mermaid")
    doc = json.loads(render_architecture(empty, fmt="excalidraw"))
    assert doc["elements"] == []
