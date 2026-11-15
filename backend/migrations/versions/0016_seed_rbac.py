"""Seed empat peran aplikasi dan matriks izin

Jira: DIG-90. Nilai ditulis langsung di migrasi (bukan diimpor dari kode aplikasi) agar
riwayat migrasi tidak berubah saat kode berubah. Tes memastikan isinya sama dengan
app/modules/auth/permissions.py.

Revision ID: 0016
Revises: 0015
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS = [
    (
        "master_data:read",
        "Melihat master data proyek, anggota, peran, level kompleksitas, dan hari libur",
    ),
    ("master_data:write", "Menambah, mengubah, dan menghapus master data (F1)"),
    ("import:run", "Menjalankan impor Project Plan, Trello, dan TeamGit (F2)"),
    ("data_quality:read", "Melihat laporan kualitas data dan baris yang ditolak"),
    (
        "work_event:write",
        "Mencatat CR, blocker, overrun, hotfix, ketidakhadiran, rotasi, dan pengalihan task (F3)",
    ),
    ("task_status:update_own", "Memperbarui status task miliknya sendiri (F3)"),
    (
        "baseline:read",
        "Melihat halaman baseline Digital Twin: ringkasan, timeline, dependency, "
        "dan process map (F4)",
    ),
    (
        "workload:read_all",
        "Melihat beban kerja dan ketidakhadiran seluruh anggota (heatmap RLI dan D-09)",
    ),
    ("workload:read_own", "Melihat task dan beban kerja miliknya sendiri"),
    ("event_log:export", "Mengekspor event log ke format XES"),
    ("user:manage", "Mengelola akun pengguna dan peran aplikasinya"),
]

ROLES = [
    ("kaur_asman", "Kaur/Asman", "Memantau progres dan beban kerja seluruh proyek aktif"),
    (
        "system_analyst",
        "System Analyst",
        "Menganalisis proses, ketergantungan, dan beban kerja, serta mencatat perubahan",
    ),
    (
        "anggota_tim",
        "Anggota Tim Pengembang",
        "Melihat task dan beban miliknya sendiri serta memperbarui status task",
    ),
    ("admin_data", "Administrator Data", "Mengelola impor data, master data, dan akun pengguna"),
]

MATRIX = {
    "kaur_asman": [
        "master_data:read",
        "baseline:read",
        "workload:read_all",
        "workload:read_own",
        "work_event:write",
    ],
    "system_analyst": [
        "master_data:read",
        "baseline:read",
        "workload:read_all",
        "workload:read_own",
        "work_event:write",
        "data_quality:read",
        "event_log:export",
    ],
    "anggota_tim": [
        "master_data:read",
        "baseline:read",
        "workload:read_own",
        "task_status:update_own",
    ],
    "admin_data": [
        "master_data:read",
        "master_data:write",
        "import:run",
        "data_quality:read",
        "event_log:export",
        "user:manage",
    ],
}


def upgrade() -> None:
    permission = sa.table(
        "permission", sa.column("permission_code", sa.String), sa.column("description", sa.String)
    )
    app_role = sa.table(
        "app_role",
        sa.column("role_code", sa.String),
        sa.column("role_name", sa.String),
        sa.column("description", sa.String),
    )
    role_permission = sa.table(
        "role_permission",
        sa.column("role_code", sa.String),
        sa.column("permission_code", sa.String),
    )
    op.bulk_insert(permission, [{"permission_code": c, "description": d} for c, d in PERMISSIONS])
    op.bulk_insert(
        app_role, [{"role_code": c, "role_name": n, "description": d} for c, n, d in ROLES]
    )
    op.bulk_insert(
        role_permission,
        [
            {"role_code": role, "permission_code": perm}
            for role, perms in MATRIX.items()
            for perm in perms
        ],
    )


def downgrade() -> None:
    # Peran yang masih dipakai pengguna tidak bisa dihapus (FK RESTRICT), jadi lepaskan dulu.
    op.execute("DELETE FROM user_app_role")
    op.execute("DELETE FROM role_permission")
    op.execute("DELETE FROM app_role")
    op.execute("DELETE FROM permission")
