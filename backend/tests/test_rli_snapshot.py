"""DIG-192: snapshot RLI dan view resource_load_index sama dengan heatmap DIG-188."""

from datetime import date

from sqlalchemy import text

from app.modules.digital_twin.rli_config import FORMULA_VERSION
from app.modules.digital_twin.rli_snapshot import refresh
from tests.conftest import REQUIRES_DB
from tests.test_heatmap_api import team  # noqa: F401  (fixture)

pytestmark = REQUIRES_DB

AS_OF = date(2026, 3, 4)


VIEW = text("SELECT * FROM resource_load_index ORDER BY resource_id, week_start")


def view_rows(db) -> list:
    return db.execute(VIEW).all()


def test_view_matches_heatmap_endpoint(client, db, team):  # noqa: F811
    count = refresh(db, AS_OF)
    db.commit()
    heatmap = client.get(
        "/api/v1/digital-twin/workload-heatmap",
        params={"start": "2026-02-02", "weeks": 26, "as_of": AS_OF.isoformat()},
    ).json()
    expected = {
        (row["resource_id"], cell["week_start"]): (cell["rli"], cell["category"])
        for row in heatmap["rows"]
        for cell in row["cells"]
    }
    rows = view_rows(db)
    assert count == len(rows) == len(expected) > 0
    actual = {
        (r.resource_id, r.week_start.isoformat()): (
            None if r.rli is None else float(r.rli),
            r.category,
        )
        for r in rows
    }
    assert actual == expected
    assert {(r.formula_version, r.provisional, r.as_of) for r in rows} == {
        (FORMULA_VERSION, heatmap["provisional"], AS_OF)
    }
    assert all((r.week_end - r.week_start).days == 4 for r in rows)


def test_refresh_replaces_previous_snapshot(db, team):  # noqa: F811
    first = refresh(db, AS_OF)
    db.commit()
    assert refresh(db, date(2026, 3, 11)) == first
    db.commit()
    assert len(view_rows(db)) == first
    assert {r.as_of for r in view_rows(db)} == {date(2026, 3, 11)}


def test_jc_app_can_only_read_the_view(db):
    privileges = {
        p: db.scalar(text(f"SELECT has_table_privilege('jc_app', 'resource_load_index', '{p}')"))
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
    }
    assert privileges == {"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False}
