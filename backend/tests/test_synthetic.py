"""Tes generator data sintetis DIG-16 (DIG-81, DIG-82, DIG-83)."""

import csv
import json
import re
from datetime import date
from pathlib import Path

import pytest

from synthetic import reference as ref
from synthetic.checks import find_problems, read_tables
from synthetic.final_sources import write_final_sources
from synthetic.raw_sources import PLAN_HEADER, write_raw_sources
from synthetic.world import build_world

AS_OF = date(2026, 11, 6)


@pytest.fixture(scope="module")
def world():
    return build_world(42, AS_OF)


@pytest.fixture(scope="module")
def output(world, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("synthetic")
    write_final_sources(world, out / "final_sources")
    write_raw_sources(world, out / "raw")
    return out


def test_same_seed_gives_identical_files(tmp_path):
    for name in ("a", "b"):
        generated = build_world(7, AS_OF)
        write_final_sources(generated, tmp_path / name / "final_sources")
        write_raw_sources(generated, tmp_path / name / "raw")
    for file in sorted((tmp_path / "a").rglob("*.*")):
        twin = tmp_path / "b" / file.relative_to(tmp_path / "a")
        assert file.read_bytes() == twin.read_bytes(), file.name


@pytest.mark.parametrize("seed", [42, 7, 2026])
def test_clean_final_sources_follow_data_dictionary(seed, tmp_path):
    write_final_sources(build_world(seed, AS_OF), tmp_path)
    assert find_problems(tmp_path) == []


def test_eleven_files_with_data_dictionary_headers(output):
    for table, header in ref.HEADERS.items():
        with (output / "final_sources" / f"{table}.csv").open(encoding="utf-8") as handle:
            assert next(csv.reader(handle)) == header


def test_scenarios_from_acceptance_criteria_are_present(output):
    t = read_tables(output / "final_sources")
    assert any(r["secondary_role_ids"] for r in t["resources"]), "peran rangkap"
    takeovers = [r for r in t["assignments"] if r["is_takeover"] == "true"]
    assert takeovers, "takeover"
    absences = {r["absence_type"] for r in t["availability"]}
    assert set(ref.ENUMS[("availability", "absence_type")]) <= absences
    events = t["change_events"]
    assert {r["event_type"] for r in events} == set(ref.ENUMS[("change_events", "event_type")])
    assert {r["decision"] for r in events} - {""} == set(ref.ENUMS[("change_events", "decision")])
    modes = {r["resolution_mode"] for r in events} - {""}
    assert modes == set(ref.ENUMS[("change_events", "resolution_mode")])
    assert {r["dependency_type"] for r in t["task_dependencies"]} == {"hard", "soft"}
    assert any(r["is_hotfix"] == "true" for r in t["workload_items"]), "hotfix"
    statuses = {r["status"] for r in t["tasks"]}
    assert {"done", "in_progress", "blocked", "on_hold", "dropped", "not_started"} <= statuses
    project_statuses = {r["status"] for r in t["projects"]}
    assert {"released", "development", "planning", "on_hold"} <= project_statuses


def test_takeover_releases_previous_assignment(output):
    t = read_tables(output / "final_sources")
    for takeover in (r for r in t["assignments"] if r["is_takeover"] == "true"):
        earlier = [
            r
            for r in t["assignments"]
            if r["task_id"] == takeover["task_id"] and r["is_takeover"] == "false"
        ]
        assert earlier and earlier[0]["released_date"] != ""


def test_planned_dates_skip_weekends_and_holidays(world):
    holidays = {day for day, _ in ref.HOLIDAYS}
    for task in world.tasks:
        for day in (task.planned_start, task.planned_finish):
            assert day.weekday() < 5 and day not in holidays, task.task_id


def test_nothing_happens_after_as_of(output):
    t = read_tables(output / "final_sources")
    for row in t["tasks"]:
        for column in ("actual_start", "actual_finish"):
            assert row[column] == "" or date.fromisoformat(row[column]) <= AS_OF
    assert all(date.fromisoformat(r["event_date"]) <= AS_OF for r in t["change_events"])


def test_raw_sources_cover_the_same_tasks(world, output):
    raw = output / "raw"
    visible = {t.task_id for t in world.tasks if t.min_start <= AS_OF}
    plan_codes = set()
    for file in sorted((raw / "project_plan").glob("*.csv")):
        with file.open(encoding="utf-8") as handle:
            reader = csv.reader(handle)
            assert next(reader) == PLAN_HEADER
            plan_codes |= {row[1] for row in reader}
    assert plan_codes == visible

    board = json.loads((raw / "trello" / "trello_board.json").read_text(encoding="utf-8"))
    card_codes = {c["name"].split(" | ")[0] for c in board["cards"]}
    assert {t.task_id for t in world.tasks if t.actual_start} <= card_codes
    assert {a["type"] for a in board["actions"]} >= {"createCard", "updateCard", "addMemberToCard"}

    codes = set()
    for log in (raw / "git").glob("*.log"):
        codes |= set(re.findall(r"\[(TSK-\d{4})\]", log.read_text(encoding="utf-8")))
    assert codes and codes <= {t.task_id for t in world.tasks}


def test_identity_map_differs_per_tool(world, output):
    with (output / "ground_truth" / "identity_map.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["resource_id"] for r in rows] == [r.resource_id for r in world.resources]
    for row in rows:
        assert len({row["project_plan_pic"], row["trello_username"], row["git_author"]}) == 3
