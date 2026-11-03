"""Seed data referensi D-03 roles dan D-04 complexity_levels

Jira: DIG-78.

Sumber nilai:
- roles: daftar ID dari Data Dictionary; nama dan deskripsi peran dari wawancara
  dengan Tim DEVTI PuTI (sheet "Diskusi dgn PuTI", A.2). capacity_reference memakai
  default 3.0 dari Data Dictionary.
- complexity_levels: ID dan nama dari Data Dictionary dan wawancara (Bagian C).
  min_days, max_days, dan load_weight adalah ASUMSI TIM, bukan data PuTI. Nilainya
  diubah lewat endpoint DIG-104 dan difinalkan bersama tWinner pada DIG-186.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Salinan statis; migrasi tidak mengimpor model agar tetap stabil saat model berubah.
roles = sa.table(
    "roles",
    sa.column("role_id", sa.String),
    sa.column("role_name", sa.String),
    sa.column("capacity_reference", sa.Double),
    sa.column("description", sa.Text),
)
complexity_levels = sa.table(
    "complexity_levels",
    sa.column("complexity_id", sa.String),
    sa.column("complexity_name", sa.String),
    sa.column("min_days", sa.Double),
    sa.column("max_days", sa.Double),
    sa.column("load_weight", sa.Double),
)

ROLES = [
    (
        "ROLE-KAUR",
        "Kepala Urusan / Asisten Manajer",
        "Mengawasi jalannya proyek dari sisi manajemen dan kebijakan organisasi.",
    ),
    (
        "ROLE-SA",
        "System Analyst",
        "Memimpin diskusi teknis, mematangkan proses bisnis, melakukan breakdown task, "
        "dan memimpin penentuan estimasi kompleksitas fitur bersama tim.",
    ),
    (
        "ROLE-TW",
        "Technical Writer",
        "Mendokumentasikan hasil requirement gathering dan dokumentasi teknis aplikasi.",
    ),
    (
        "ROLE-UIUX",
        "UI/UX Designer",
        "Merancang antarmuka dan pengalaman pengguna berdasarkan proses bisnis "
        "yang telah disepakati.",
    ),
    (
        "ROLE-QA",
        "Quality Assurance",
        "Menguji fitur yang selesai dikembangkan untuk memastikan produk bebas dari bug.",
    ),
    (
        "ROLE-FE",
        "Front-End Developer",
        "Mengembangkan sisi antarmuka dan tampilan fitur aplikasi.",
    ),
    (
        "ROLE-BE",
        "Back-End Developer",
        "Mengembangkan sisi server dan integrasi logika sistem untuk mendukung "
        "kebutuhan data Front-End.",
    ),
    (
        "ROLE-DM",
        "Data Manager",
        "Merancang, membuat, dan mengelola struktur basis data utama aplikasi.",
    ),
]

# (id, nama, min_days, max_days, load_weight). Angka = asumsi tim, lihat docstring.
COMPLEXITY_LEVELS = [
    ("CX-VH", "Very High", 10.0, 20.0, 2.0),
    ("CX-H", "High", 5.0, 10.0, 1.5),
    ("CX-M", "Medium", 2.0, 5.0, 1.0),
    ("CX-L", "Low", 0.5, 2.0, 0.5),
]


def upgrade() -> None:
    op.bulk_insert(
        roles,
        [
            {
                "role_id": role_id,
                "role_name": name,
                "capacity_reference": 3.0,
                "description": description,
            }
            for role_id, name, description in ROLES
        ],
    )
    op.bulk_insert(
        complexity_levels,
        [
            {
                "complexity_id": complexity_id,
                "complexity_name": name,
                "min_days": min_days,
                "max_days": max_days,
                "load_weight": load_weight,
            }
            for complexity_id, name, min_days, max_days, load_weight in COMPLEXITY_LEVELS
        ],
    )


def downgrade() -> None:
    op.execute(
        complexity_levels.delete().where(
            complexity_levels.c.complexity_id.in_([row[0] for row in COMPLEXITY_LEVELS])
        )
    )
    op.execute(roles.delete().where(roles.c.role_id.in_([row[0] for row in ROLES])))
