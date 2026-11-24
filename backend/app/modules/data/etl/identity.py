"""Entity resolution identitas sumber ke D-02 `resources` lewat `resource_alias` (DIG-131).

Satu-satunya aturan pencocokan adalah `resource_alias_service.alias_key`, yang sama dengan
endpoint alias dan daftar identitas belum terpetakan (DIG-111). Tidak ada pencocokan kabur:
identitas yang belum dipetakan dilaporkan sebagai `Problem` dan `resource_id`-nya dibiarkan
kosong, sehingga aturan kelengkapan DIG-31 menolak baris itu sampai aliasnya dipetakan.
"""

from collections.abc import Mapping
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.enums import IdentitySource
from app.modules.data.etl.normalize import Candidates, Problem
from app.modules.data.resource_alias_models import ResourceAlias
from app.modules.data.resource_alias_service import alias_key

AliasIndex = Mapping[tuple[str, str], str]  # (source, alias_key) -> resource_id


def load_alias_index(db: Session) -> dict[tuple[str, str], str]:
    rows = db.execute(
        select(ResourceAlias.source, ResourceAlias.alias_key, ResourceAlias.resource_id)
    )
    return {(source, key): resource_id for source, key, resource_id in rows}


def resolve(index: AliasIndex, source: IdentitySource | str, value: str | None) -> str | None:
    """`resource_id` untuk identitas `value` dari `source`, atau None bila belum dipetakan."""
    if not value or not value.strip():
        return None
    try:
        key = alias_key(source, value)
    except ValueError:  # misalnya id member Trello yang bukan 24 heksadesimal
        return None
    return index.get((IdentitySource(source).value, key))


def resolve_plan_assignments(candidates: Candidates, index: AliasIndex) -> Candidates:
    """Isi `resource_id` kandidat assignment Project Plan dari kolom PIC. Fungsi murni."""
    rows = []
    problems = list(candidates.problems)
    for row in candidates.tables["assignments"]:
        pic = row.values.get("pic", "")
        resource_id = resolve(index, IdentitySource.PROJECT_PLAN, pic)
        if resource_id is None:
            problems.append(
                Problem(
                    "project_plan",
                    row.number,
                    row.values.get("task_id") or None,
                    "resource_id",
                    pic,
                    f"PIC '{pic}' belum dipetakan ke anggota tim (resource_alias)",
                )
            )
        rows.append(replace(row, values={**row.values, "resource_id": resource_id or ""}))
    tables = {**candidates.tables, "assignments": rows}
    return Candidates(tables=tables, problems=problems)
