"""Daftar izin dan matriks peran aplikasi (DIG-90).

Diturunkan dari Tabel 2.1 dan 2.2 (FR-01 sampai FR-12) dokumen Rancangan Kebutuhan dan
Arsitektur, proposal subbab II.2.10, serta Story DIG-19:
- Kaur/Asman dan System Analyst melihat baseline, beban kerja, dan ketidakhadiran seluruh
  anggota, serta mencatat kejadian perubahan (FR-05) dan ketidakhadiran/rotasi (FR-06).
- Anggota tim pengembang melihat beban miliknya dan mencatat kejadian perubahan pada task
  miliknya (FR-05, Tabel 2.1). Batas "miliknya" dicek di endpoint.
- Administrator data mengelola master data, impor, kualitas data, dan ekspor event log (FR-07).
- Admin IT mengelola akun pengguna dan peran aplikasinya.

Prinsip least privilege: peran hanya mendapat izin yang dibutuhkan tugasnya. Nilai di sini
harus sama dengan seed migrasi 0016; tes memastikan keduanya tidak berbeda.
"""

from enum import StrEnum


class Perm(StrEnum):
    MASTER_DATA_READ = "master_data:read"
    MASTER_DATA_WRITE = "master_data:write"
    IMPORT_RUN = "import:run"
    DATA_QUALITY_READ = "data_quality:read"
    CHANGE_EVENT_WRITE = "change_event:write"
    CHANGE_EVENT_WRITE_OWN = "change_event:write_own"
    AVAILABILITY_WRITE = "availability:write"
    BASELINE_READ = "baseline:read"
    WORKLOAD_READ_ALL = "workload:read_all"
    WORKLOAD_READ_OWN = "workload:read_own"
    EVENT_LOG_EXPORT = "event_log:export"
    USER_MANAGE = "user:manage"


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.MASTER_DATA_READ: "Melihat master data proyek, anggota, peran, level kompleksitas, "
    "dan hari libur",
    Perm.MASTER_DATA_WRITE: "Menambah, mengubah, dan menghapus master data (F1)",
    Perm.IMPORT_RUN: "Menjalankan impor Project Plan, Trello, dan TeamGit (F2)",
    Perm.DATA_QUALITY_READ: "Melihat laporan kualitas data dan baris yang ditolak",
    Perm.CHANGE_EVENT_WRITE: "Mencatat kejadian perubahan (CR, blocker, overrun, hotfix) "
    "pada task mana pun (FR-05)",
    Perm.CHANGE_EVENT_WRITE_OWN: "Mencatat kejadian perubahan pada task miliknya sendiri (FR-05)",
    Perm.AVAILABILITY_WRITE: "Mencatat ketidakhadiran dan rotasi anggota (FR-06)",
    Perm.BASELINE_READ: "Melihat halaman baseline Digital Twin: ringkasan, timeline, "
    "dependency, dan process map (F4)",
    Perm.WORKLOAD_READ_ALL: "Melihat beban kerja dan ketidakhadiran seluruh anggota "
    "(heatmap RLI dan D-09)",
    Perm.WORKLOAD_READ_OWN: "Melihat task dan beban kerja miliknya sendiri",
    Perm.EVENT_LOG_EXPORT: "Mengekspor event log ke format XES",
    Perm.USER_MANAGE: "Mengelola akun pengguna dan peran aplikasinya",
}

# kode peran: (nama, deskripsi, izin)
ROLES: dict[str, tuple[str, str, frozenset[Perm]]] = {
    "kaur_asman": (
        "Kaur/Asman",
        "Memantau progres dan beban kerja seluruh proyek aktif serta mencatat perubahan",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.BASELINE_READ,
                Perm.WORKLOAD_READ_ALL,
                Perm.WORKLOAD_READ_OWN,
                Perm.CHANGE_EVENT_WRITE,
                Perm.AVAILABILITY_WRITE,
            }
        ),
    ),
    "system_analyst": (
        "System Analyst",
        "Menganalisis proses, ketergantungan, dan beban kerja, serta mencatat perubahan",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.BASELINE_READ,
                Perm.WORKLOAD_READ_ALL,
                Perm.WORKLOAD_READ_OWN,
                Perm.CHANGE_EVENT_WRITE,
                Perm.AVAILABILITY_WRITE,
                Perm.DATA_QUALITY_READ,
            }
        ),
    ),
    "anggota_tim": (
        "Anggota Tim Pengembang",
        "Melihat beban miliknya sendiri dan mencatat kejadian perubahan pada task miliknya",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.WORKLOAD_READ_OWN,
                Perm.CHANGE_EVENT_WRITE_OWN,
            }
        ),
    ),
    "admin_data": (
        "Administrator Data",
        "Mengelola master data, impor, kualitas data, dan ekspor event log",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.MASTER_DATA_WRITE,
                Perm.IMPORT_RUN,
                Perm.DATA_QUALITY_READ,
                Perm.EVENT_LOG_EXPORT,
            }
        ),
    ),
    "admin_it": (
        "Admin IT",
        "Mengelola akun pengguna dan peran aplikasinya",
        frozenset({Perm.USER_MANAGE}),
    ),
}
