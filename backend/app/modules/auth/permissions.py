"""Daftar izin dan matriks peran aplikasi (DIG-90).

Diturunkan dari proposal subbab II.2.10 dan III.1 serta Story DIG-19:
- Kaur/Asman dan System Analyst melihat beban kerja dan ketidakhadiran seluruh anggota.
- Anggota tim pengembang hanya melihat task dan beban miliknya.
- Administrator data mengelola impor, master data, dan akun pengguna.

Prinsip least privilege: peran hanya mendapat izin yang dibutuhkan tugasnya. Nilai di sini
harus sama dengan seed migrasi 0016; tes memastikan keduanya tidak berbeda.
"""

from enum import StrEnum


class Perm(StrEnum):
    MASTER_DATA_READ = "master_data:read"
    MASTER_DATA_WRITE = "master_data:write"
    IMPORT_RUN = "import:run"
    DATA_QUALITY_READ = "data_quality:read"
    WORK_EVENT_WRITE = "work_event:write"
    TASK_STATUS_UPDATE_OWN = "task_status:update_own"
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
    Perm.WORK_EVENT_WRITE: "Mencatat CR, blocker, overrun, hotfix, ketidakhadiran, rotasi, "
    "dan pengalihan task (F3)",
    Perm.TASK_STATUS_UPDATE_OWN: "Memperbarui status task miliknya sendiri (F3)",
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
        "Memantau progres dan beban kerja seluruh proyek aktif",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.BASELINE_READ,
                Perm.WORKLOAD_READ_ALL,
                Perm.WORKLOAD_READ_OWN,
                Perm.WORK_EVENT_WRITE,
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
                Perm.WORK_EVENT_WRITE,
                Perm.DATA_QUALITY_READ,
                Perm.EVENT_LOG_EXPORT,
            }
        ),
    ),
    "anggota_tim": (
        "Anggota Tim Pengembang",
        "Melihat task dan beban miliknya sendiri serta memperbarui status task",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.BASELINE_READ,
                Perm.WORKLOAD_READ_OWN,
                Perm.TASK_STATUS_UPDATE_OWN,
            }
        ),
    ),
    "admin_data": (
        "Administrator Data",
        "Mengelola impor data, master data, dan akun pengguna",
        frozenset(
            {
                Perm.MASTER_DATA_READ,
                Perm.MASTER_DATA_WRITE,
                Perm.IMPORT_RUN,
                Perm.DATA_QUALITY_READ,
                Perm.EVENT_LOG_EXPORT,
                Perm.USER_MANAGE,
            }
        ),
    ),
}
