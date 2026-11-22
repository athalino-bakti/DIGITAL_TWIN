"""DIG-142: deteksi siklus task_dependencies dengan graf kecil."""

import copy

from app.modules.data.quality.cycles import Edge, id_order, resolve_cycles
from app.modules.data.quality.rules import validate_final_sources
from tests.test_quality_rules import CLEAN, to_tables


def edges(*pairs: tuple[str, str, str]) -> list[Edge]:
    return [Edge(*pair) for pair in pairs]


def closing_ids(graph: list[Edge]) -> list[str]:
    return [graph[c.closing].edge_id for c in resolve_cycles(graph)]


def test_no_cycle():
    graph = edges(("DEP-001", "B", "A"), ("DEP-002", "C", "B"), ("DEP-003", "C", "A"))
    assert resolve_cycles(graph) == []


def test_two_node_cycle_rejects_the_newest_edge():
    graph = edges(("DEP-153", "TSK-0118", "TSK-0117"), ("DEP-154", "TSK-0117", "TSK-0118"))
    [cycle] = resolve_cycles(graph)
    assert graph[cycle.closing].edge_id == "DEP-154"
    assert sorted(cycle.members) == [0, 1]
    assert cycle.path[0] == cycle.path[-1]


def test_three_node_cycle():
    graph = edges(("DEP-001", "B", "A"), ("DEP-002", "C", "B"), ("DEP-003", "A", "C"))
    [cycle] = resolve_cycles(graph)
    assert graph[cycle.closing].edge_id == "DEP-003"
    assert len(cycle.members) == 3
    assert set(cycle.path) == {"A", "B", "C"}


def test_two_separate_cycles():
    graph = edges(
        ("DEP-001", "B", "A"),
        ("DEP-002", "A", "B"),
        ("DEP-010", "D", "C"),
        ("DEP-009", "C", "D"),
        ("DEP-003", "E", "A"),
    )
    assert sorted(closing_ids(graph)) == ["DEP-002", "DEP-010"]


def test_overlapping_cycles_remove_one_edge_at_a_time():
    # A -> B -> A dan A -> B -> C -> A berbagi edge A -> B.
    graph = edges(("DEP-001", "A", "B"), ("DEP-002", "B", "A"), ("DEP-003", "B", "C"))
    graph += edges(("DEP-004", "C", "A"))
    rejected = closing_ids(graph)
    remaining = [e for e in graph if e.edge_id not in rejected]
    assert resolve_cycles(remaining) == []
    assert len(rejected) == 2


def test_id_order_is_numeric():
    assert id_order(Edge("DEP-99", "A", "B")) < id_order(Edge("DEP-154", "A", "B"))
    assert id_order(Edge("DEP-0099", "A", "B")) < id_order(Edge("DEP-154", "A", "B"))


def test_self_dependency_is_left_to_the_value_rule():
    assert resolve_cycles(edges(("DEP-001", "A", "A"))) == []


def test_soft_cycle_is_rejected_too():
    data = copy.deepcopy(CLEAN)
    data["task_dependencies"][0].update(dependency_type="soft", propagation_factor="0.3")
    data["task_dependencies"].append(
        {
            "dependency_id": "DEP-002",
            "task_id": "TSK-0001",
            "depends_on_task_id": "TSK-0002",
            "dependency_type": "soft",
            "propagation_factor": "0.3",
        }
    )
    findings = validate_final_sources(to_tables(data)).findings
    by_rule = {(f.rule_id, f.row_key, f.level) for f in findings}
    assert by_rule == {
        ("DQ-DEP-012", "DEP-002", "tolak"),
        ("DQ-DEP-013", "DEP-001", "peringatan"),
    }
    closing = next(f for f in findings if f.rule_id == "DQ-DEP-012")
    assert closing.message in (
        "Menutup siklus TSK-0002 -> TSK-0001 -> TSK-0002",
        "Menutup siklus TSK-0001 -> TSK-0002 -> TSK-0001",
    )
