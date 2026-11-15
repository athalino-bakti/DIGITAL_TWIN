"""DIG-168: directly-follows graph dari trace, tanpa basis data."""

from datetime import UTC, datetime, timedelta

from app.modules.digital_twin.process_map import (
    Hidden,
    Step,
    directly_follows,
    filter_by_frequency,
)

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def trace(*items: tuple[str, float]) -> list[Step]:
    """(aktivitas, jam sejak T0)."""
    return [Step(activity, T0 + timedelta(hours=hours)) for activity, hours in items]


def edge(pm, source, target):
    return next(e for e in pm.edges if (e.source, e.target) == (source, target))


def node(pm, activity):
    return next(n for n in pm.nodes if n.activity == activity)


TRACES = {
    "TSK-0001": trace(("Dibuat", 0), ("To Do", 2), ("Done", 12)),
    "TSK-0002": trace(("Dibuat", 0), ("To Do", 4), ("Done", 10)),
    "TSK-0003": trace(("Dibuat", 0), ("To Do", 9)),
    "TSK-0004": trace(("Dibuat", 0)),
}


def test_pairs_are_counted_per_occurrence_and_per_case():
    pm = directly_follows(TRACES)
    assert [(e.source, e.target, e.frequency, e.cases) for e in pm.edges] == [
        ("Dibuat", "To Do", 3, 3),
        ("To Do", "Done", 2, 2),
    ]
    assert (pm.cases, pm.events, pm.max_edge_frequency) == (4, 9, 3)


def test_mean_and_median_gap_in_hours():
    pm = directly_follows(TRACES)
    first = edge(pm, "Dibuat", "To Do")  # 2, 4, 9 jam: jumlah ganjil
    assert (first.mean_hours, first.median_hours) == (5.0, 4.0)
    second = edge(pm, "To Do", "Done")  # 10 dan 6 jam: jumlah genap
    assert (second.mean_hours, second.median_hours) == (8.0, 8.0)


def test_nodes_count_events_cases_starts_and_ends():
    pm = directly_follows(TRACES)
    created = node(pm, "Dibuat")
    assert (created.frequency, created.cases, created.start_cases, created.end_cases) == (
        4,
        4,
        4,
        1,
    )
    todo = node(pm, "To Do")
    assert (todo.start_cases, todo.end_cases) == (0, 1)
    assert [n.activity for n in pm.nodes] == ["Dibuat", "To Do", "Done"]


def test_single_event_case_is_start_and_end_without_edges():
    pm = directly_follows({"TSK-0001": trace(("Dibuat", 0))})
    assert pm.edges == []
    only = node(pm, "Dibuat")
    assert (only.start_cases, only.end_cases, pm.max_edge_frequency) == (1, 1, 0)


def test_self_loop_and_repeat_in_one_case():
    pm = directly_follows(
        {"TSK-0001": trace(("In Progress", 0), ("In Progress", 1), ("QA", 3), ("In Progress", 4))}
    )
    loop = edge(pm, "In Progress", "In Progress")
    assert (loop.frequency, loop.cases, loop.mean_hours) == (1, 1, 1.0)
    progress = node(pm, "In Progress")
    assert (progress.frequency, progress.cases) == (3, 1)


def test_pair_repeated_in_one_case_counts_one_case():
    pm = directly_follows({"TSK-0001": trace(("A", 0), ("B", 1), ("A", 2), ("B", 4))})
    ab = edge(pm, "A", "B")
    assert (ab.frequency, ab.cases, ab.mean_hours, ab.median_hours) == (2, 1, 1.5, 1.5)


def test_empty_traces():
    pm = directly_follows({"TSK-0001": []})
    assert (pm.nodes, pm.edges, pm.cases, pm.events, pm.max_edge_frequency) == ([], [], 0, 0, 0)
    assert directly_follows({}).cases == 0


def test_filter_hides_rare_edges_and_orphan_nodes():
    traces = {
        **TRACES,
        "TSK-0005": trace(("Dibuat", 0), ("Kartu diarsipkan", 5)),
    }
    pm, hidden = filter_by_frequency(directly_follows(traces), 2)
    assert [(e.source, e.target) for e in pm.edges] == [("Dibuat", "To Do"), ("To Do", "Done")]
    assert "Kartu diarsipkan" not in {n.activity for n in pm.nodes}
    assert hidden == Hidden(edges=1, nodes=1, edge_frequency=1)
    assert pm.max_edge_frequency == 3  # tetap dari sebelum filter


def test_frequent_node_stays_when_its_edges_are_hidden():
    traces = {f"TSK-{i:04d}": trace(("Dibuat", 0)) for i in range(1, 4)}
    traces["TSK-0009"] = trace(("Dibuat", 0), ("To Do", 1))
    pm, hidden = filter_by_frequency(directly_follows(traces), 3)
    assert [n.activity for n in pm.nodes] == ["Dibuat"]
    assert hidden == Hidden(edges=1, nodes=1, edge_frequency=1)


def test_min_frequency_one_changes_nothing():
    full = directly_follows(TRACES)
    pm, hidden = filter_by_frequency(full, 1)
    assert pm == full
    assert hidden == Hidden()
