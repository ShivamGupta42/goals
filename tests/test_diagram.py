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


def test_punctuation_colliding_ids_do_not_merge() -> None:
    # 'a-b' and 'a.b' both sanitize to 'a_b'; they must stay distinct.
    amap = GoalArchitectureMap(
        title="t",
        overview="o",
        nodes=[
            ArchitectureNode(node_id="a-b", label="dash", plain_summary="x"),
            ArchitectureNode(node_id="a.b", label="dot", plain_summary="x"),
        ],
        edges=[ArchitectureEdge(from_node="a-b", to_node="a.b", relation="to")],
    )
    doc = json.loads(render_architecture(amap, fmt="excalidraw"))
    rect_ids = [e["id"] for e in doc["elements"] if e["type"] == "rectangle"]
    assert len(rect_ids) == len(set(rect_ids)) == 2  # no duplicate/merged ids
    mermaid = render_architecture(amap, fmt="mermaid")
    assert mermaid.count('["dash"]') == 1 and mermaid.count('["dot"]') == 1


def test_mermaid_collapses_newlines_and_semicolons() -> None:
    amap = GoalArchitectureMap(
        title="t",
        overview="o",
        nodes=[ArchitectureNode(node_id="n", label="line1\nline2; tail", plain_summary="x")],
        edges=[],
    )
    out = render_architecture(amap, fmt="mermaid")
    assert "\n" not in out.split('["', 1)[1].split('"]', 1)[0]  # label has no raw newline
    assert ";" not in out.split('["', 1)[1].split('"]', 1)[0]  # no statement separator in label


def test_excalidraw_elbow_arrow_points_are_orthogonal_across_rows() -> None:
    # ui->api->db places db a row below api: the api->db arrow must elbow, not go diagonal.
    doc = json.loads(render_architecture(_map(), fmt="excalidraw"))
    arrows = [e for e in doc["elements"] if e["type"] == "arrow"]
    for arrow in arrows:
        pts = arrow["points"]
        # consecutive segments are axis-aligned (only one of dx/dy nonzero each)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            assert x0 == x1 or y0 == y1


def test_empty_map_does_not_crash() -> None:
    empty = GoalArchitectureMap(title="t", overview="o", nodes=[], edges=[])
    assert "flowchart TD" in render_architecture(empty, fmt="mermaid")
    doc = json.loads(render_architecture(empty, fmt="excalidraw"))
    assert doc["elements"] == []
