"""Ketidakhadiran satu anggota tidak boleh bertumpuk di D-09 availability

Jira: DIG-106 (review PR #13). Aturan "periode ketidakhadiran anggota yang sama tidak
boleh bertumpuk" sebelumnya hanya dicek di service, sehingga dua permintaan bersamaan
untuk anggota dan tanggal yang sama bisa sama-sama tersimpan. Exclusion constraint
menutup celah itu di basis data. rotation_in dikecualikan karena berarti anggota hadir
(masuk dari tim lain), bukan tidak hadir. Kolom D-09 tidak berubah.

btree_gist dibutuhkan agar kolom teks `resource_id` bisa dibandingkan dengan `=` di
dalam indeks GiST bersama rentang tanggal. Extension ini termasuk trusted extension
sejak PostgreSQL 13, sehingga cukup dibuat oleh pemilik database. Downgrade hanya
menghapus constraint dan membiarkan extension, karena extension bisa dipakai objek lain.

Nomor 0017 mengikuti antrean migrasi tim (0007-0016 sudah dipesan PR lain). Sebelum
merge, `down_revision` disesuaikan dengan head `main` saat itu.

Revision ID: 0017
Revises: 0008
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "ex_availability_no_overlap"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        f"ALTER TABLE availability ADD CONSTRAINT {CONSTRAINT} "
        "EXCLUDE USING gist (resource_id WITH =, daterange(date_start, date_end, '[]') WITH &&) "
        "WHERE (absence_type <> 'rotation_in')"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE availability DROP CONSTRAINT {CONSTRAINT}")
