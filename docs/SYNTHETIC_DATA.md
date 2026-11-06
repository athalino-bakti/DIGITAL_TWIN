# Generator Data Sintetis

Generator di `backend/synthetic/` menghasilkan data pengembangan selama J&C tidak menerima data sistem PuTI secara langsung (DIG-16). Satu dunia simulasi Tim DEVTI dibangun dari seed yang sama, lalu ditulis dalam tiga bentuk: final sources sesuai Data Dictionary, sumber mentah, dan salinan kotor untuk menguji validasi.

Seluruh nama orang, proyek, dan unit pemilik proses adalah fiktif. Skenario kerjanya mengikuti hasil wawancara dengan Tim DEVTI PuTI. Data ini tidak memuat data pribadi sebenarnya sesuai UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi.

## Menjalankan

Dari folder `backend/` (PowerShell atau bash), tanpa dependency tambahan:

```powershell
.\.venv\Scripts\python.exe -m synthetic --out synthetic-output --seed 42 --as-of 2026-11-06 --dirty
```

| Parameter | Default | Fungsi |
|---|---|---|
| `--out` | `synthetic-output` | Folder keluaran (diabaikan Git) |
| `--seed` | `42` | Seed acak; seed yang sama selalu menghasilkan berkas yang identik |
| `--as-of` | `2026-11-06` | Tanggal acuan: realisasi, kejadian, dan penugasan berhenti di tanggal ini |
| `--dirty` | mati | Tulis juga salinan kotor beserta manifest cacat |

## Keluaran

```text
synthetic-output/
  manifest.json                 # seed, as_of, jumlah baris, catatan skenario
  final_sources/                # 11 CSV D-01 s.d. D-11 (projects.csv ... holidays.csv)
  raw/
    project_plan/               # project_plan_PRJ-xxx.csv per proyek (ekspor Google Sheets)
    trello/trello_board.json    # ekspor papan Trello: lists, labels, members, cards, actions
    git/PRJ-xxx.log             # git log per repositori proyek
  ground_truth/identity_map.csv # pemetaan resource_id ke nama di Project Plan, Trello, dan Git
  dirty/                        # hanya dengan --dirty
    final_sources/              # 11 CSV dengan cacat
    raw/                        # Project Plan, Trello, dan git log dengan cacat
    manifest_cacat.csv          # daftar cacat: sumber, berkas, lokasi, kolom, jenis, nilai asli, nilai kotor
```

**Final sources** mengikuti nama tabel, urutan kolom, format ID, dan nilai enum Data Dictionary. Seluruh CSV bersih dapat dimuat langsung ke skema hasil migrasi DIG-15 tanpa melanggar constraint.

**Sumber mentah** memakai format yang disusun tim untuk simulasi:

| Sumber | Format |
|---|---|
| Project Plan | Header berbahasa Indonesia, tanggal `dd/mm/yyyy`, desimal koma, status seperti "Dikerjakan" dan "Selesai", kolom `Kode` berisi `task_id`, kolom `Bergantung Pada` berisi `TSK-xxxx (hard); TSK-yyyy (soft)` |
| Trello | Satu papan dengan list Backlog, To Do, In Progress, Blocked, Hold, QA, Done. Nama kartu `TSK-xxxx \| nama task` atau `WLI-xxxx \| judul` untuk beban non-proyek. Label `operasional`, `tiket`, `hotfix`, dan `severity: ...` |
| Git | Format bawaan `git log --date=iso-strict`. Sebagian besar pesan commit memuat `[TSK-xxxx]`, sebagian tidak |

Identitas anggota sengaja berbeda di tiap tool, misalnya "Sari P." di Project Plan, `saripusp` di Trello, dan `sarip <sari.puspitasari@devti.example>` di Git. `ground_truth/identity_map.csv` menjadi kunci jawaban untuk tes alias identitas (DIG-24).

## Skenario yang dimuat

| Skenario dari wawancara | Wujud di data |
|---|---|
| Breakdown task per peran | Setiap fitur dipecah menjadi task planning, uiux, dm_dev, be_dev, fe_dev, testing, bugfix, documentation |
| Dependency hard dan soft | BE menunggu DM (hard); FE membuat dummy saat DM bekerja (soft); fitur interaktif FE menunggu BE (hard) |
| Peran rangkap dan lintas peran | `secondary_role_ids` (SA rangkap FE atau DM, BE rangkap DM) dan `cross_role_capable` |
| Cuti terencana, cuti hamil | `availability` dengan `is_known_at_planning = true`; jadwal rencana sudah menghindarinya |
| Cuti mendadak, rotasi keluar | `availability` dengan `is_known_at_planning = false`; task yang sedang berjalan dialihkan (`assignments.is_takeover = true`) |
| Anggota baru | `join_date` baru dan `rotation_in` |
| Change request | `change_events` dengan keputusan `accept_now`, `defer_next`, `reject` dan mode `scope_addition`, `swap_task`, `extend_duration`; task yang ditukar berstatus `dropped` |
| Perubahan prioritas | Satu proyek ditunda (`on_hold`) dengan mode `reshuffle` |
| Blocker dan overrun | Satu task `blocked` pada tanggal acuan, blocker yang sudah selesai, dan event `overrun` untuk task yang melewati estimasi |
| Hotfix | Tiket `critical` dengan `is_hotfix = true` pada aplikasi yang sudah rilis, beserta event `hotfix` |
| Beban non-proyek | `workload_items` operasional dan tiket; tiket berseverity rendah mulai dikerjakan lebih lambat |
| Hari libur | Libur nasional dan cuti bersama 2026 menurut SKB 3 Menteri; jadwal rencana tidak jatuh pada hari libur |

## Data kotor

| Jenis | Contoh |
|---|---|
| `format_tanggal` | `05/10/2026`, `5 Okt 2026`, `2026/10/05` di kolom tanggal |
| `alias_berbeda` | PIC "Sari", "SARI PUSPITASARI", akun Trello kedua, email Git berbeda |
| `duplikat` | Baris task, workload, Project Plan, atau aksi Trello tercatat dua kali |
| `siklus_dependency` | Task A bergantung pada B dan B bergantung pada A |
| `wajib_kosong` | `estimated_days`, `join_date`, atau kolom Estimasi kosong |
| `fk_tidak_dikenal` | `RES-099`, `TSK-9999`, atau PIC yang tidak ada di daftar anggota |
| `enum` | Status `selesai`, severity `urgent` |
| `format_id` | `AVL-9` |
| `urutan_tanggal` | `date_end` lebih awal dari `date_start` |
| `kode_task_hilang` | Kartu Trello tanpa kode task |

Dua jenis cacat pada final sources tidak dapat dicegah oleh constraint basis data, sehingga validator J&C yang menangkapnya: `siklus_dependency` (DIG-142) dan `format_tanggal` (DIG-141). PostgreSQL menerima sebagian tanggal non-ISO dan dapat salah membacanya, misalnya `01/12/2026` tersimpan sebagai 2026-01-12. Cacat lain pada final sources ditolak oleh constraint skema DIG-15.

## Asumsi

1. Rentang hari dan bobot `complexity_levels` serta `capacity_reference` mengikuti dataset dummy dosbim (`puti_datasets.xlsx`), sama dengan seed migrasi 0007.
2. Satu anggota mengerjakan satu task pada satu waktu. Beban paralel dicatat lewat `workload_items`.
3. Durasi aktual berkisar 0,8 sampai 1,2 kali estimasi, dan sekitar 12% task mengalami overrun 1,5 sampai 2 kali estimasi.

## Pemakaian bersama tWinner

tWinner dapat memakai `final_sources/` sebagai dataset baseline atau memuatnya ke basis data bersama. Kedua tim cukup menyepakati `--seed` dan `--as-of` agar dataset yang dipakai sama persis.
