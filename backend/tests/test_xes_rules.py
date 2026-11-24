"""DIG-172: serializer XES, tanpa basis data."""

from datetime import UTC, datetime, timedelta, timezone
from xml.etree.ElementTree import fromstring

import pytest

from app.modules.data import xes
from app.modules.data.xes import XesEvent, serialize, to_xes

WIB = timezone(timedelta(hours=7))


def event(case="TSK-0001", activity="Kerjakan", at=None, **extra) -> XesEvent:
    return XesEvent(case, activity, at or datetime(2026, 3, 2, 9, 0, tzinfo=WIB), **extra)


def parse(events):
    return fromstring(to_xes(events).encode("utf-8"))


def attrs(element) -> dict[str, str]:
    return {child.get("key"): child.get("value") for child in element if child.get("key")}


def test_log_structure_follows_the_schema_order():
    log = parse([event()])
    assert log.tag == "log"
    assert log.get("xes.version") == xes.XES_VERSION
    order = [child.tag for child in log]
    # extension*, global*, classifier*, atribut log, trace*
    assert order == ["extension"] * 4 + ["global"] * 2 + ["classifier"] + ["string"] * 2 + ["trace"]
    assert {(e.get("name"), e.get("prefix"), e.get("uri")) for e in log.iter("extension")} == {
        ("Concept", "concept", "http://www.xes-standard.org/concept.xesext"),
        ("Time", "time", "http://www.xes-standard.org/time.xesext"),
        ("Lifecycle", "lifecycle", "http://www.xes-standard.org/lifecycle.xesext"),
        ("Organizational", "org", "http://www.xes-standard.org/org.xesext"),
    }
    trace_global, event_global = log.findall("global")
    assert trace_global.get("scope") == "trace" and attrs(trace_global) == {
        "concept:name": "__INVALID__"
    }
    assert event_global.get("scope") == "event"
    assert set(attrs(event_global)) == {"concept:name", "time:timestamp", "lifecycle:transition"}
    assert log.find("classifier").get("keys") == "concept:name"


def test_event_attributes():
    log = parse(
        [
            event(
                project_id="PRJ-001",
                activity_kind="status",
                resource_id="RES-007",
                actor_name="Sari",
                role_id="ROLE-BE",
                source="trello",
                source_ref="a" * 24,
            )
        ]
    )
    trace = log.find("trace")
    assert attrs(trace) == {"concept:name": "TSK-0001", "project_id": "PRJ-001"}
    item = trace.find("event")
    assert attrs(item) == {
        "concept:name": "Kerjakan",
        "lifecycle:transition": "complete",
        "time:timestamp": "2026-03-02T09:00:00.000+07:00",
        "org:resource": "RES-007",
        "org:role": "ROLE-BE",
        "activity_kind": "status",
        "source": "trello",
        "source_ref": "a" * 24,
    }
    assert item.find("date").get("key") == "time:timestamp"


def test_optional_attributes_are_left_out_when_empty():
    item = parse([event(actor_name="", role_id=None)]).find("trace/event")
    assert set(attrs(item)) == {"concept:name", "lifecycle:transition", "time:timestamp"}
    assert attrs(parse([event()]).find("trace")) == {"concept:name": "TSK-0001"}


def test_actor_name_is_used_when_resource_is_unknown():
    item = parse([event(actor_name="akun-trello")]).find("trace/event")
    assert attrs(item)["org:resource"] == "akun-trello"


def test_special_characters_are_escaped():
    name = 'Uji <b>&"kutip"\' & dan >'
    document = to_xes([event(activity=name, actor_name="A&B <x>")])
    assert "<b>" not in document
    item = fromstring(document.encode("utf-8")).find("trace/event")
    assert attrs(item)["concept:name"] == name
    assert attrs(item)["org:resource"] == "A&B <x>"


def test_timestamps_keep_their_time_zone():
    log = parse([event(at=datetime(2026, 3, 2, 2, 0, tzinfo=UTC))])
    assert attrs(log.find("trace/event"))["time:timestamp"] == "2026-03-02T02:00:00.000+00:00"
    with pytest.raises(ValueError, match="zona waktu"):
        to_xes([event(at=datetime(2026, 3, 2, 9, 0))])


def test_events_are_sorted_by_time_within_a_trace():
    later, earlier = datetime(2026, 3, 3, tzinfo=WIB), datetime(2026, 3, 2, tzinfo=WIB)
    log = parse(
        [
            event(activity="B", at=later),
            event(activity="A", at=earlier),
            event(activity="C", at=later, event_id=9),
        ]
    )
    assert [attrs(e)["concept:name"] for e in log.iter("event")] == ["A", "B", "C"]


def test_one_trace_per_case():
    log = parse([event("TSK-0001"), event("TSK-0001"), event("TSK-0002")])
    assert [attrs(t)["concept:name"] for t in log.findall("trace")] == ["TSK-0001", "TSK-0002"]
    assert [len(t.findall("event")) for t in log.findall("trace")] == [2, 1]


def test_empty_log_has_no_trace():
    log = parse([])
    assert log.findall("trace") == []
    assert len(log.findall("extension")) == 4


def test_output_is_streamed_per_trace():
    chunks = list(serialize([event("TSK-0001"), event("TSK-0002")]))
    assert len(chunks) == 1 + 2 + 1  # header, dua trace, penutup
    assert chunks[0].startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert chunks[-1] == "</log>\n"
