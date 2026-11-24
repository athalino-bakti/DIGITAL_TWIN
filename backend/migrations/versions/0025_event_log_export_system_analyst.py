"""System Analyst boleh mengekspor event log (event_log:export)

Jira: DIG-39. Story DIG-39 ("Sebagai System Analyst, saya ingin mengekspor event log ke XES")
butuh izin event_log:export pada peran system_analyst; seed 0016 hanya memberikannya ke
admin_data. Matriks di app/modules/auth/permissions.py ikut diubah, dan test_rbac memastikan
keduanya sama.

Nomor 0025 karena 0024 dipakai #53 (data_quality_result). Selama #53 belum merge, migrasi ini
menyambung ke 0023; setelah #53 merge, `down_revision` cukup diganti ke "0024".

Revision ID: 0025
Revises: 0024
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0025"
down_revision: Union[str, Sequence[str], None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO role_permission (role_code, permission_code) "
        "VALUES ('system_analyst', 'event_log:export')"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission "
        "WHERE role_code = 'system_analyst' AND permission_code = 'event_log:export'"
    )
