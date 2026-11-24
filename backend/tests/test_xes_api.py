"""DIG-173: GET /api/v1/data/event-log.xes terhadap PostgreSQL sungguhan."""

from datetime import datetime, timedelta, timezone
from xml.etree.ElementTree import fromstring

import pytest
from sqlalchemy import text

from tests.conftest import REQUIRES_DB, make_token
from tests.test_resources_api import create as create_member

pytestmark = REQUIRES_DB

URL = "/api/v1/data/event-log.xes"
INSERT = text(
    "INSERT INTO event_log (case_id, project_id, activity, activity_kind, event_time, "
    "resource_id, actor_name, source, source_ref) VALUES (:case, :project, :activity, 'status', "
    ":at, :resource, :actor, 'trello', :ref)"
)


@pytest.fixture
def log(client, db) -> str:
    db.execute(text("TRUNCATE event_log RESTART IDENTITY"))
    rid = create_member(client)["resource_id"]
    rows = [
        ("TSK-0002", "PRJ-002", "Selesai", "2026-09-03T10:00:00+07:00", None, "akun & tim"),
        ("TSK-0001", "PRJ-001", "Kerjakan", "2026-09-02T09:00:00+07:00", rid, None),
        ("TSK-0001", "PRJ-001", "Task dibuat", "2026-09-01T09:00:00+07:00", rid, None),
    ]
    for number, (case, project, activity, at, resource, actor) in enumerate(rows):
        db.execute(
            INSERT,
            {
                "case": case,
                "project": project,
                "activity": activity,
                "at": at,
                "resource": resource,
                "actor": actor,
                "ref": f"{number:024d}",
            },
        )
    db.commit()
    yield rid
    db.execute(text("TRUNCATE event_log RESTART IDENTITY"))
    db.commit()


def values(element) -> dict[str, str]:
    return {child.get("key"): child.get("value") for child in element if child.get("key")}


def test_xes_download(client, log):
    response = client.get(URL)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/xml")
    assert 'filename="event_log.xes"' in response.headers["content-disposition"]
    document = fromstring(response.content)
    traces = document.findall("trace")
    assert [values(t)["concept:name"] for t in traces] == ["TSK-0001", "TSK-0002"]
    first = traces[0].findall("event")
    assert [values(e)["concept:name"] for e in first] == ["Task dibuat", "Kerjakan"]
    stamp = datetime.fromisoformat(values(first[0])["time:timestamp"])
    assert stamp == datetime(2026, 9, 1, 9, 0, tzinfo=timezone(timedelta(hours=7)))
    assert (values(first[0])["org:resource"], values(first[0])["org:role"]) == (log, "ROLE-BE")
    # Tanpa resource_id: nama akun sumber dipakai, peran tidak diisi.
    other = values(traces[1].find("event"))
    assert other["org:resource"] == "akun & tim" and "org:role" not in other


def test_xes_filters_match_the_json_endpoint(client, log):
    response = client.get(URL, params={"project_id": "PRJ-002"})
    assert 'filename="event_log_PRJ-002.xes"' in response.headers["content-disposition"]
    assert [values(t)["concept:name"] for t in fromstring(response.content).findall("trace")] == [
        "TSK-0002"
    ]
    ranged = client.get(URL, params={"date_from": "2026-09-02", "date_to": "2026-09-02"})
    assert len(fromstring(ranged.content).findall("trace/event")) == 1
    bad = client.get(URL, params={"date_from": "2026-09-03", "date_to": "2026-09-01"})
    assert bad.status_code == 422


def test_empty_xes_is_still_a_valid_log(client, db):
    db.execute(text("TRUNCATE event_log RESTART IDENTITY"))
    db.commit()
    document = fromstring(client.get(URL).content)
    assert document.tag == "log" and document.findall("trace") == []


@pytest.mark.parametrize(("role", "code"), [("admin_data", 200), ("system_analyst", 200)])
def test_xes_needs_event_log_export(client, db, role, code):
    token = make_token(db, f"xes-{role}", [role])
    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == code
