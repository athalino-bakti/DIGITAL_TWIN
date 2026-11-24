"""DIG-185: CPM dan propagasi dampak keterlambatan. Tanpa basis data."""

import pytest

from app.modules.digital_twin.cpm import (
    CycleError,
    Edge,
    critical_path,
    propagate_delay,
    topological_order,
)


def hard(depends_on, task_id):
    return Edge(depends_on, task_id, True, 1.0)


def soft(depends_on, task_id, factor=0.3):
    return Edge(depends_on, task_id, False, factor)


# Contoh buku teks:  A(3) -> B(2) -> D(4)
#                    A(3) -> C(6) -> D(4)      jalur kritis A-C-D = 13 hari, B punya float 4
DURATIONS = {"A": 3, "B": 2, "C": 6, "D": 4}
EDGES = [hard("A", "B"), hard("A", "C"), hard("B", "D"), hard("C", "D")]


def test_topological_order_is_stable_and_respects_dependencies():
    assert topological_order(DURATIONS, EDGES) == ["A", "B", "C", "D"]
    assert topological_order(["Z", "Y"], []) == ["Y", "Z"]


def test_topological_order_ignores_edges_to_unknown_tasks():
    assert topological_order(["A", "B"], [hard("A", "B"), hard("X", "A")]) == ["A", "B"]


def test_cycle_is_reported_with_the_tasks_involved():
    with pytest.raises(CycleError) as error:
        topological_order(["A", "B", "C"], [hard("A", "B"), hard("B", "C"), hard("C", "B")])
    assert error.value.task_ids == ["B", "C"]


def test_forward_and_backward_pass():
    cpm = critical_path(DURATIONS, EDGES)
    assert (cpm["A"].earliest_start, cpm["A"].earliest_finish) == (0, 3)
    assert (cpm["C"].earliest_start, cpm["C"].earliest_finish) == (3, 9)
    assert (cpm["D"].earliest_start, cpm["D"].earliest_finish) == (9, 13)
    assert (cpm["B"].earliest_start, cpm["B"].latest_start, cpm["B"].latest_finish) == (3, 7, 9)
    assert cpm["B"].total_float == 4


def test_critical_tasks_have_zero_float():
    cpm = critical_path(DURATIONS, EDGES)
    assert [task for task in sorted(cpm) if cpm[task].is_critical] == ["A", "C", "D"]


def test_soft_dependency_does_not_hold_the_schedule():
    cpm = critical_path({"A": 5, "B": 2}, [soft("A", "B")])
    assert cpm["B"].earliest_start == 0
    assert cpm["A"].is_critical and not cpm["B"].is_critical
    assert cpm["B"].total_float == 3


def test_independent_tasks_and_empty_project():
    cpm = critical_path({"A": 2, "B": 5}, [])
    assert cpm["B"].is_critical and cpm["A"].total_float == 3
    assert critical_path({}, []) == {}


def test_fractional_durations():
    cpm = critical_path({"A": 0.5, "B": 2.5}, [hard("A", "B")])
    assert cpm["B"].earliest_finish == 3.0
    assert cpm["A"].is_critical and cpm["B"].is_critical


def test_hard_cycle_raises():
    with pytest.raises(CycleError):
        critical_path({"A": 1, "B": 1}, [hard("A", "B"), hard("B", "A")])


# --- propagasi ---


def test_hard_dependency_passes_the_full_delay():
    assert propagate_delay("A", 4, [hard("A", "B"), hard("B", "C")]) == {"B": 4, "C": 4}


def test_soft_dependency_passes_a_fraction():
    impact = propagate_delay("A", 10, [soft("A", "B"), hard("B", "C"), soft("C", "D")])
    assert impact == pytest.approx({"B": 3.0, "C": 3.0, "D": 0.9})


def test_largest_impact_wins_when_paths_meet():
    edges = [hard("A", "B"), soft("A", "C"), hard("B", "D"), hard("C", "D")]
    assert propagate_delay("A", 10, edges) == pytest.approx({"B": 10, "C": 3, "D": 10})


def test_only_descendants_are_affected():
    edges = [hard("A", "B"), hard("X", "A"), hard("Y", "Z")]
    assert propagate_delay("A", 2, edges) == {"B": 2}


def test_finished_tasks_are_not_affected_and_stop_the_propagation():
    edges = [hard("A", "B"), hard("B", "C"), soft("A", "C")]
    assert propagate_delay("A", 10, edges, finished={"B"}) == pytest.approx({"C": 3.0})


def test_finished_source_still_propagates():
    """Task yang selesai terlambat tetap berdampak ke turunannya."""
    assert propagate_delay("A", 2, [hard("A", "B")], finished={"A"}) == {"B": 2}


@pytest.mark.parametrize("delay", [0, -3])
def test_no_delay_no_impact(delay):
    assert propagate_delay("A", delay, [hard("A", "B")]) == {}


def test_task_without_dependencies():
    assert propagate_delay("A", 5, []) == {}
