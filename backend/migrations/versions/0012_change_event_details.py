"""change_event_details: persetujuan dan waktu selesai kejadian perubahan

Jira: DIG-221. Tabel pendukung J&C yang dibaca tWinner (docs/DATA_CONTRACT.md bagian 7.1),
dengan struktur bagian 7.3. Satu baris melengkapi satu event_id D-10 dengan penyetuju CR atau
perubahan prioritas, tanggal persetujuan, dan tanggal blocker, overrun, atau hotfix selesai.

Detail ikut terhapus bersama kejadiannya (ON DELETE CASCADE). Anggota yang tercatat sebagai
penyetuju tidak bisa dihapus (ON DELETE RESTRICT). Aturan "approved_date dan resolved_date
tidak sebelum event_date" sengaja tidak dibuat constraint karena event_date ada di D-10; aturan
itu dicek validator J&C (app.modules.data.change_event_detail_rules).

Revision ID: 0012
Revises: 0011
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "change_event_details",
        sa.Column("event_id", sa.String(length=20), nullable=False),
        sa.Column("approved_by_resource_id", sa.String(length=20), nullable=True),
        sa.Column("approved_date", sa.Date(), nullable=True),
        sa.Column("resolved_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["change_events.event_id"],
            name=op.f("fk_change_event_details_event_id_change_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_resource_id"],
            ["resources.resource_id"],
            name=op.f("fk_change_event_details_approved_by_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_change_event_details")),
    )
    op.create_index(
        op.f("ix_change_event_details_approved_by_resource_id"),
        "change_event_details",
        ["approved_by_resource_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_change_event_details_approved_by_resource_id"),
        table_name="change_event_details",
    )
    op.drop_table("change_event_details")
