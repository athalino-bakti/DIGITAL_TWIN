# Katalog aturan kualitas data (DIG-31)

Aturan validasi J&C untuk final sources D-01 sampai D-11, staging Trello, dan currentness impor. Aturan disusun dari Data Dictionary dan diberi karakteristik kualitas data ISO/IEC 25012. Kode ada di `backend/app/modules/data/quality/`. Tes `test_quality_catalog.py` memastikan setiap `rule_id` di katalog ini ada di kode, dan sebaliknya.

Proposal III.1 memakai empat karakteristik ISO/IEC 25012. Maknanya di sini, dengan kata sendiri:

| Karakteristik | Makna dalam validator ini |
|---|---|
| *completeness* | nilai yang wajib ada memang terisi |
| *consistency* | nilai sesuai aturan format, daftar nilai, rujukan antartabel, dan aturan logika antarkolom, sehingga tidak saling bertentangan |
| *currentness* | data cukup baru untuk dipakai: kapan terakhir diimpor dan seberapa baru isi sumbernya |
| *traceability* | ada jejak siapa yang mencatat atau meminta suatu perubahan |

Tingkat:
- **tolak**: baris tidak boleh dimuat ke final sources (ETL DIG-134 melewatkannya, DIG-145 menyimpannya di `rejected_row`).
- **peringatan**: baris tetap dimuat, tetapi temuan dicatat untuk ditinjau.

Validator hanya menilai. Ia tidak mengubah nilai dan tidak menulis ke tabel mana pun.

## Sasaran pemeriksaan

| Sasaran | Adapter | Keterangan |
|---|---|---|
| CSV final sources | `sources.read_csv_folder` | Enam sampai sebelas berkas `<tabel>.csv` (wireframe FR-01, keluaran generator `final_sources/`) |
| Workbook final sources | `sources.read_workbook` | Sheet `<tabel>` atau `<tabel>_csv` (dataset dummy dosbim), dipakai untuk uji lokal |
| Tabel final sources di basis data | `sources.read_database` | Menangkap aturan yang lolos constraint: siklus, hari libur, rentang estimasi, `requested_by` |
| Staging Trello | `sources.read_trello_cards` | Satu baris per kartu (nama terakhir) |
| `import_job` dan staging | `currentness.measure` | Satu baris per sumber impor |

Semua aturan baris berlaku untuk ketiga sasaran final sources. Untuk tabel di basis data, aturan yang sudah dijaga constraint selalu lolos.

## Aturan umum per tabel

Nomor aturan seragam antartabel: `DQ-<TBL>-NNN`. Sebuah tabel hanya mendapat nomor yang berlaku untuknya (lihat daftar aturan).

| No | Aturan | Karakteristik | Tingkat | Dasar | Dijaga constraint DB |
|---|---|---|---|---|---|
| 001 | Kolom wajib tidak kosong | completeness | tolak | DD kolom Wajib, kontrak §5 dan §6, AC DIG-31 | ya (NOT NULL) |
| 002 | Format ID sesuai pola (PK, serta `secondary_role_ids`) | consistency | tolak | kontrak §5, AC DIG-31 | ya (`ck_*_format`) |
| 003 | Nilai enum termasuk daftar nilai | consistency | tolak | kontrak §6, AC DIG-31 | ya (`ck_*_valid`) |
| 004 | Referensi FK dikenal di dataset yang sama | consistency | tolak | kontrak §6, AC DIG-31 | ya (FK) |
| 005 | PK tidak muncul dua kali; kemunculan kedua dan seterusnya ditolak | consistency | tolak | kontrak §6, AC DIG-31 (baris ganda) | ya (PK) |
| 006 | Isi baris identik dengan baris lain yang PK-nya berbeda | consistency | peringatan | AC DIG-31 (baris ganda), wireframe FR-01 | tidak |
| 007 | Tanggal berformat ISO `YYYY-MM-DD` | consistency | tolak | kontrak §5, AC DIG-31 | tidak (PostgreSQL menerima sebagian format lain) |
| 008 | Bilangan bulat, desimal bertitik, atau boolean `true`/`false` sesuai tipe DD | consistency | tolak | kontrak §5 | ya (tipe kolom) |
| 009 | Urutan tanggal: akhir tidak lebih awal dari awal | consistency | tolak | kontrak §6 (`ck_*_after_*`), AC DIG-31 | ya |
| 010 | Aturan nilai yang juga dijaga CHECK basis data | consistency | tolak | kontrak §6 | ya |

Rincian aturan 010:

| Tabel | Aturan |
|---|---|
| `projects` | `priority_rank >= 1` |
| `roles` | `capacity_reference > 0` |
| `complexity_levels` | `min_days >= 0`, `max_days >= min_days`, `load_weight >= 0` |
| `tasks` | `priority_rank >= 1`, `estimated_days > 0`, `qa_reject_count >= 0` |
| `task_dependencies` | `0 < propagation_factor <= 1`, hard berarti `propagation_factor = 1.0`, task tidak bergantung pada dirinya sendiri |
| `change_events` | `extension_days >= 0` |

## Daftar aturan

Kolom "Sasaran": CSV = CSV/workbook final sources, DB = tabel final sources, STG = staging, JOB = `import_job`, ETL = kandidat ETL DIG-134 dibandingkan dengan isi basis data. Semua aturan final sources berlaku untuk CSV dan DB.

| rule_id | Tabel.kolom | Aturan | Karakteristik | Tingkat | Dasar | Constraint DB | Sasaran | Tiket |
|---|---|---|---|---|---|---|---|---|
| DQ-PRJ-001 | projects.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD, AC | ya | CSV, DB | DIG-140 |
| DQ-PRJ-002 | projects.project_id | Format `PRJ-001` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-PRJ-003 | projects.status | Enum status proyek | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-PRJ-005 | projects.project_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-PRJ-006 | projects.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-PRJ-007 | projects.start_date, target_launch_date, actual_launch_date | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-PRJ-008 | projects.priority_rank, dor_fulfilled | Tipe bilangan bulat dan boolean | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-PRJ-009 | projects.start_date ≤ target_launch_date, actual_launch_date | Urutan tanggal | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-141 |
| DQ-PRJ-010 | projects.priority_rank | `>= 1` | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-RES-001 | resources.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD, AC | ya | CSV, DB | DIG-140 |
| DQ-RES-002 | resources.resource_id, secondary_role_ids | Format `RES-001`, `ROLE-DM;ROLE-FE` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-RES-003 | resources.seniority | Enum seniority | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-RES-004 | resources.primary_role_id | Rujukan ke roles | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-RES-005 | resources.resource_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-RES-006 | resources.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-RES-007 | resources.join_date | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-RES-008 | resources.cross_role_capable | Boolean | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-ROL-001 | roles.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-ROL-002 | roles.role_id | Format `ROLE-<KODE>` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-ROL-005 | roles.role_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-ROL-006 | roles.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-ROL-008 | roles.capacity_reference | Desimal | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-ROL-010 | roles.capacity_reference | `> 0` | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-CPX-001 | complexity_levels.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-CPX-002 | complexity_levels.complexity_id | Format `CX-<KODE>` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-CPX-005 | complexity_levels.complexity_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-CPX-006 | complexity_levels.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-CPX-008 | complexity_levels.min_days, max_days, load_weight | Desimal | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-CPX-010 | complexity_levels.min_days, max_days, load_weight | Rentang nilai | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-TSK-001 | tasks.* wajib (`project_id`, `required_role_id`, `complexity_id`, `estimated_days`, `planned_start`, `planned_finish`, ...) | Kolom wajib tidak kosong | completeness | tolak | DD, AC | ya | CSV, DB | DIG-140 |
| DQ-TSK-002 | tasks.task_id | Format `TSK-0001` | consistency | tolak | kontrak §5, AC | ya | CSV, DB | DIG-140 |
| DQ-TSK-003 | tasks.phase, status | Enum phase dan status | consistency | tolak | kontrak §6, AC | ya | CSV, DB | DIG-140 |
| DQ-TSK-004 | tasks.project_id, required_role_id, complexity_id | Rujukan ke projects, roles, complexity_levels | consistency | tolak | kontrak §6, AC | ya | CSV, DB | DIG-140 |
| DQ-TSK-005 | tasks.task_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-TSK-006 | tasks.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-TSK-007 | tasks.planned_start, planned_finish, actual_start, actual_finish | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-TSK-008 | tasks.priority_rank, estimated_days, qa_reject_count, dod_fulfilled | Tipe bilangan dan boolean | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-TSK-009 | tasks.planned_start ≤ planned_finish, actual_start ≤ actual_finish | Urutan tanggal | consistency | tolak | kontrak §6, AC | ya | CSV, DB | DIG-141 |
| DQ-TSK-010 | tasks.priority_rank, estimated_days, qa_reject_count | Rentang nilai | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-TSK-011 | tasks.actual_finish | `actual_finish` butuh `actual_start` | consistency | tolak | kontrak §6, AC | ya | CSV, DB | DIG-141 |
| DQ-TSK-012 | tasks.planned_start, planned_finish | Tidak jatuh di D-11 holidays | consistency | peringatan | AC, keputusan Davi | tidak | CSV, DB | DIG-141 |
| DQ-TSK-013 | tasks.estimated_days | Dalam `min_days` s.d. `max_days` kompleksitasnya | consistency | peringatan | AC | tidak | CSV, DB | DIG-141 |
| DQ-TSK-014 | tasks.task_id | `task_id` belum dipakai task milik proyek lain di basis data | consistency | tolak | review #61, kontrak §6 (`task_id` PK global) | tidak | ETL | DIG-134 |
| DQ-DEP-001 | task_dependencies.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-DEP-002 | task_dependencies.dependency_id | Format `DEP-001` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-DEP-003 | task_dependencies.dependency_type | Enum hard/soft | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-DEP-004 | task_dependencies.task_id, depends_on_task_id | Rujukan ke tasks | consistency | tolak | kontrak §6, AC | ya | CSV, DB | DIG-140 |
| DQ-DEP-005 | task_dependencies.dependency_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-DEP-008 | task_dependencies.propagation_factor | Desimal | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-DEP-010 | task_dependencies.propagation_factor, task_id | Rentang, hard = 1.0, bukan diri sendiri | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-DEP-011 | task_dependencies.task_id + depends_on_task_id | Pasangan tidak ganda | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-DEP-012 | task_dependencies | Edge penutup siklus (hard dan soft) | consistency | tolak | AC, keputusan Davi | tidak | CSV, DB | DIG-142 |
| DQ-DEP-013 | task_dependencies | Edge lain di dalam siklus | consistency | peringatan | AC, keputusan Davi | tidak | CSV, DB | DIG-142 |
| DQ-ASG-001 | assignments.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-ASG-002 | assignments.assignment_id | Format `ASG-0001` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-ASG-004 | assignments.task_id, resource_id, role_in_task | Rujukan ke tasks, resources, roles | consistency | tolak | kontrak §6, wireframe FR-01 | ya | CSV, DB | DIG-140 |
| DQ-ASG-005 | assignments.assignment_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-ASG-006 | assignments.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-ASG-007 | assignments.assigned_date, released_date | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-ASG-008 | assignments.is_takeover | Boolean | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-ASG-009 | assignments.assigned_date ≤ released_date | Urutan tanggal | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-141 |
| DQ-WLI-001 | workload_items.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-WLI-002 | workload_items.item_id | Format `WLI-0001` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-WLI-003 | workload_items.item_type, severity | Enum | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-WLI-004 | workload_items.resource_id, related_project_id | Rujukan ke resources, projects | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-WLI-005 | workload_items.item_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-WLI-006 | workload_items.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-WLI-007 | workload_items.received_date, started_date, resolved_date | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-WLI-008 | workload_items.is_hotfix | Boolean | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-WLI-009 | workload_items.received_date ≤ started_date ≤ resolved_date | Urutan tanggal | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-141 |
| DQ-AVL-001 | availability.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-AVL-002 | availability.availability_id | Format `AVL-001` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-AVL-003 | availability.absence_type | Enum | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-AVL-004 | availability.resource_id | Rujukan ke resources | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-AVL-005 | availability.availability_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-AVL-006 | availability.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-AVL-007 | availability.date_start, date_end | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-AVL-008 | availability.is_known_at_planning | Boolean | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-AVL-009 | availability.date_start ≤ date_end | Urutan tanggal | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-141 |
| DQ-CHG-001 | change_events.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-CHG-002 | change_events.event_id | Format `EVT-001` | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-CHG-003 | change_events.event_type, decision, resolution_mode | Enum | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-CHG-004 | change_events.project_id, affected_task_id | Rujukan ke projects, tasks | consistency | tolak | kontrak §6, wireframe FR-01 | ya | CSV, DB | DIG-140 |
| DQ-CHG-005 | change_events.event_id | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-CHG-006 | change_events.* | Isi identik dengan PK berbeda | consistency | peringatan | AC | tidak | CSV, DB | DIG-140 |
| DQ-CHG-007 | change_events.event_date | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-CHG-008 | change_events.extension_days | Desimal | consistency | tolak | kontrak §5 | ya | CSV, DB | DIG-140 |
| DQ-CHG-010 | change_events.extension_days | `>= 0` | consistency | tolak | kontrak §6 | ya | CSV, DB | DIG-140 |
| DQ-CHG-011 | change_events.requested_by | Pencatat atau peminta perubahan terisi | traceability | peringatan | AC, keputusan Davi | tidak | CSV, DB | DIG-143 |
| DQ-HOL-001 | holidays.* wajib | Kolom wajib tidak kosong | completeness | tolak | DD | ya | CSV, DB | DIG-140 |
| DQ-HOL-005 | holidays.holiday_date | PK tidak ganda | consistency | tolak | AC | ya | CSV, DB | DIG-140 |
| DQ-HOL-007 | holidays.holiday_date | Tanggal ISO | consistency | tolak | kontrak §5 | tidak | CSV, DB | DIG-141 |
| DQ-TRL-001 | staging_trello_action.card_name | Kartu memuat kode `TSK-` atau `WLI-` di awal nama | completeness | peringatan | DIG-37 (kode task dari nama kartu), cacat `kode_task_hilang` | tidak | STG | DIG-143 |
| DQ-CUR-001 | import_job | Impor sukses terakhir per sumber paling lama 7 hari sebelum `as_of`, dan sumber pernah diimpor | currentness | peringatan | AC, kontrak §3 (ETL minimal mingguan) | tidak | JOB | DIG-143 |

## Perilaku penting

- **Rujukan FK** diperiksa terhadap seluruh ID di dataset yang sama, termasuk baris yang ditolak. Penolakan tidak berantai. ETL DIG-134 yang memutuskan nasib baris yang merujuk baris tertolak.
- **`task_id` lintas proyek (TSK-014)**: hanya berlaku di ETL, karena konteksnya kandidat satu proyek ditambah task yang sudah ada. Task milik proyek lain tidak diubah, dan dependensi serta assignment yang menunjuk `task_id` itu dilewati (`skipped_parent`). ETL tidak pernah mengubah `project_id` task yang sudah ada.
- **Baris ganda (005)**: kemunculan pertama dipertahankan, kemunculan berikutnya ditolak. Pesan menyebut apakah isinya identik, yaitu bentuk cacat `duplikat` dari generator.
- **Siklus (012/013)**: graf memakai dependency hard dan soft, karena `propagate_delay` di modul CPM juga memakai keduanya. Per siklus, edge dengan `dependency_id` terbesar (paling akhir ditambahkan) ditolak, lalu diulang sampai graf bebas siklus. Edge lain di siklus yang sama mendapat peringatan.
- **Tanggal** dibaca ketat per format sumber (`quality.dates`): ISO untuk final sources, `dd/mm/yyyy` untuk Project Plan. Nilai yang bisa ditebak tetapi bukan format sumbernya (`01/12/2026`, `28 Sep 2026`, `2026/09/09`) tetap pelanggaran. Aturan tanggal turunan (009, 011, 012, 013) dilewati bila tanggalnya sendiri tidak terbaca, karena pelanggarannya sudah tercatat di 007.
- **Skor completeness** per tabel adalah sel wajib yang terisi dibagi seluruh sel wajib. Skor keseluruhan adalah jumlah sel wajib terisi semua tabel dibagi jumlah sel wajib semua tabel.
- **Currentness** per sumber dihitung terhadap `as_of` supaya hasilnya deterministik:
  - `import_age_days`: `as_of` dikurangi tanggal (WIB) impor sukses terakhir;
  - `data_age_days`: `as_of` dikurangi aksi terbaru di staging (hanya Trello);
  - `source_lag_days`: impor terakhir dikurangi aksi terbaru (hanya Trello).

  Project Plan tidak punya cap waktu pembaruan sumber, dan TeamGit belum punya staging. Keduanya hanya dinilai dari umur impornya.

## Di luar cakupan

| Hal | Alasan |
|---|---|
| Akhir pekan pada `planned_start`/`planned_finish` | Keputusan Davi: AC hanya menyebut D-11 holidays. Dataset dosbim memuat 689 tanggal rencana di akhir pekan. |
| `alias_berbeda` (PIC, akun Trello kedua, email Git) | Pencocokan identitas ada di DIG-24 dan DIG-131 |
| Cacat staging Project Plan dan TeamGit | Adapter staging Project Plan menunggu DIG-25 masuk `main` (tiket lanjutan). TeamGit belum punya staging (DIG-27). |
| Duplikat aksi Trello | Dicegah PK `staging_trello_action` |
| `ex_availability_no_overlap`, `uq_projects_active_priority` | Dijaga constraint basis data, belum diperiksa validator |
| Jejak audit berbasis `audit_log` | Menunggu tabel `audit_log` (DIG-222). D-09 tidak punya kolom pencatat. |

## Catatan pemetaan karakteristik untuk Davi

Pemetaan di atas mengikuti AC DIG-31, dan belum diubah. Ada dua aturan yang bisa dipandang di karakteristik lain:

- **Kesesuaian sintaks** (002 format ID, 007 format tanggal, 008 tipe) bisa digolongkan sebagai akurasi sintaktik (*accuracy*) `[perlu verifikasi]`, bukan *consistency*. Kalau diubah, proposal III.1 perlu menyebut karakteristik kelima.
- **Kartu Trello tanpa kode task** (TRL-001) dicatat sebagai *completeness*, karena kode task-nya tidak ada. Ia juga bisa dipandang *consistency* terhadap konvensi penamaan kartu.
