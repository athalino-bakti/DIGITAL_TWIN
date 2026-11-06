# Data Contract J&C Power Team dan tWinner Team

Dokumen ini menjadi kesepakatan tentang data yang dibagi bersama oleh aplikasi Digital Twin PuTI milik J&C Power Team (Digital Twin Modeling & Data Integration) dan aplikasi milik tWinner Team (What-if Scenario & Decision Support). Isinya mencakup skema final sources D-01 sampai D-11, pemilik setiap tabel, hak akses, frekuensi pembaruan, aturan format data, dan tabel pendukung di luar Data Dictionary.

| Item | Nilai |
|---|---|
| Versi | 1.0 |
| Jira | DIG-12 (DIG-62, DIG-63) |
| Skema acuan | Sheet "Data Dictionary" pada berkas *Business Process DT untuk PuTI* |
| Implementasi skema | `backend/app/modules/data/models.py` dan revisi Alembic `0001` sampai `0005` (DIG-15) |
| Basis data | PostgreSQL bersama |

## 1. Ruang lingkup

J&C mengolah data dari beberapa sumber (Project Plan, riwayat kartu Trello, dan riwayat commit TeamGit) menjadi final sources sesuai Data Dictionary. tWinner memakai final sources tersebut sebagai parameter kondisi aktual untuk skenario *what-if*, perhitungan KPI, dan rekomendasi. Kedua aplikasi bertukar data melalui basis data bersama tanpa pertukaran berkas manual.

Selama pengembangan, J&C tidak menerima data sistem PuTI secara langsung. Seluruh isi tabel berasal dari simulasi mandiri dan generator data sintetis (DIG-16), dengan skenario kerja yang mengikuti hasil wawancara dengan Tim DEVTI PuTI. Data sintetis tidak memuat data pribadi sebenarnya sesuai UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi.

## 2. Pihak dan tanggung jawab

| Pihak | Peran dalam kontrak | Tanggung jawab |
|---|---|---|
| J&C Power Team | Produsen dan pemilik final sources | Membuat dan memelihara skema lewat migrasi Alembic, mengisi D-01 sampai D-11 melalui ETL dan formulir aplikasi, menjaga kualitas data (validasi ISO/IEC 25012), menyediakan akses baca dan ekspor CSV cadangan |
| tWinner Team | Konsumen final sources | Membaca final sources tanpa mengubahnya, menyimpan skenario dan hasil simulasi di tabel miliknya sendiri, memberi tahu J&C bila membutuhkan kolom atau tabel baru |

## 3. Pemilik, hak akses, dan frekuensi pembaruan

J&C memiliki seluruh tabel di bawah, dan tWinner hanya mendapat hak baca. Kolom "Sumber pengisian" menunjukkan fitur J&C yang menulis ke tabel tersebut.

| Tabel | Sumber pengisian | Frekuensi pembaruan | Hak J&C | Hak tWinner |
|---|---|---|---|---|
| D-01 `projects` | Formulir master data (F1) | Saat ada perubahan proyek atau status proyek | Baca-tulis | Baca |
| D-02 `resources` | Formulir master data (F1) | Saat ada anggota baru, perubahan peran, atau rotasi | Baca-tulis | Baca |
| D-03 `roles` | Seed migrasi, lalu formulir F1 | Saat nilai kapasitas atau deskripsi peran diubah | Baca-tulis | Baca |
| D-04 `complexity_levels` | Seed migrasi, lalu formulir F1 | Saat rentang hari atau bobot diubah | Baca-tulis | Baca |
| D-05 `tasks` | ETL Project Plan dan Trello (F2), pembaruan status (F3) | Setiap ETL dijalankan dan saat status task dicatat | Baca-tulis | Baca |
| D-06 `task_dependencies` | ETL Project Plan (F2) | Setiap ETL dijalankan | Baca-tulis | Baca |
| D-07 `assignments` | ETL Trello (F2), pengalihan task (F3) | Setiap ETL dijalankan dan saat pengalihan dicatat | Baca-tulis | Baca |
| D-08 `workload_items` | ETL Trello untuk kartu operasional dan tiket (F2) | Setiap ETL dijalankan | Baca-tulis | Baca |
| D-09 `availability` | Formulir ketidakhadiran dan rotasi (F1, F3) | Saat cuti, ketidakhadiran mendadak, atau rotasi dicatat | Baca-tulis | Baca |
| D-10 `change_events` | Formulir CR, blocker, overrun, dan hotfix (F3) | Saat kejadian dicatat | Baca-tulis | Baca |
| D-11 `holidays` | Formulir master data (F1) | Awal tahun dan saat ada penetapan cuti bersama | Baca-tulis | Baca |
| View Resource Load Index | Dihitung dari D-02 sampai D-09 | Mengikuti data terbaru setelah setiap ETL | Baca | Baca |

J&C menjalankan ETL paling sedikit satu kali per minggu selama iterasi analisis, serta sebelum setiap evaluasi iterasi pada minggu 9 dan minggu 12. Formulir F1 dan F3 menulis ke tabel saat data disimpan, sehingga tWinner dapat membaca perubahannya tanpa menunggu ETL.

## 4. Mekanisme akses

1. Kedua aplikasi memakai satu basis data PostgreSQL. Tabel J&C berada di schema `public`. tWinner menyimpan skenario dan hasil simulasinya di schema `twinner` miliknya sendiri, dan J&C tidak menulis ke schema tersebut.
2. Aplikasi tWinner terhubung dengan role basis data `twinner_reader`. Role ini hanya mendapat hak `SELECT` pada objek yang tercantum di bagian 3 dan bagian 7.1, tanpa hak `INSERT`, `UPDATE`, `DELETE`, maupun DDL.
3. Aplikasi J&C memakai role `jc_app` untuk baca-tulis data. J&C mengubah struktur tabel hanya lewat migrasi Alembic di repository `DIGITAL_TWIN`, tanpa perintah SQL manual.
4. Sebagai cadangan, J&C menyediakan ekspor 11 berkas CSV final sources dengan nama dan urutan kolom sesuai Data Dictionary (DIG-193).
5. J&C membagikan kredensial koneksi di luar repository. Kredensial tidak ditulis di kode, berkas `.env.example`, maupun dokumen ini.

## 5. Aturan format data

| Aspek | Aturan |
|---|---|
| Nama tabel dan kolom | Sama persis dengan Data Dictionary, huruf kecil dengan garis bawah |
| Format ID | `PRJ-001`, `RES-001`, `TSK-0001`, `DEP-001`, `ASG-0001`, `WLI-0001`, `AVL-001`, `EVT-001` dengan jumlah digit tetap; `ROLE-<KODE>` dan `CX-<KODE>` dengan kode huruf kapital |
| Nilai enum | Huruf kecil dengan garis bawah, sesuai daftar nilai pada bagian 6 |
| Tanggal | Tipe `DATE`, format ISO 8601 `YYYY-MM-DD` pada CSV, tanpa komponen jam |
| Boolean | `true` atau `false` |
| Bilangan desimal | Tipe `DOUBLE PRECISION`, titik sebagai pemisah desimal pada CSV |
| Nilai kosong | `NULL` di basis data dan sel kosong di CSV, hanya untuk kolom yang tidak wajib |
| `secondary_role_ids` | Daftar `role_id` dipisah titik koma tanpa spasi, misalnya `ROLE-DM;ROLE-FE` |
| CSV | UTF-8, pemisah koma, baris pertama berisi nama kolom |

Aturan di basis data (CHECK constraint, foreign key, dan unique constraint) menolak baris yang melanggar format ID, nilai enum, kolom wajib, dan referensi antartabel. Validator dan importer J&C yang menegakkan format tanggal. Constraint basis data tidak dipakai untuk aturan ini karena PostgreSQL menerima sebagian tanggal non-ISO (`14 Oct 2026`, `2026/09/10`, `01/12/2026`) dan dapat salah membacanya: `01/12/2026` tersimpan sebagai 2026-01-12. Validator J&C menyaring data kotor dari sumber mentah di tabel staging sebelum memuatnya ke final sources, sehingga tWinner hanya membaca baris yang lolos validasi.

## 6. Salinan Data Dictionary

Kolom "Tipe DD" dan "Keterangan" disalin dari Data Dictionary. Kolom "Tipe PostgreSQL", "Wajib", dan daftar aturan menunjukkan implementasinya di basis data.

### D-01 `projects`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `project_id` (PK) | string | VARCHAR(20) | Ya | Format PRJ-001 |
| `project_name` | string | VARCHAR(200) | Ya | Nama aplikasi |
| `process_owner` | string | VARCHAR(200) | Ya | Unit pemilik proses yang mengajukan aplikasi |
| `priority_rank` | integer | INTEGER | Ya | Angka 1 adalah prioritas tertinggi antar proyek aktif |
| `start_date` | date | DATE | Ya | Tanggal mulai perencanaan |
| `target_launch_date` | date | DATE | Ya | Target launching yang disepakati dengan pemilik proses |
| `actual_launch_date` | date | DATE | Tidak | Kosong untuk proyek yang masih berjalan |
| `status` | enum | VARCHAR(20) | Ya | planning, development, testing, released, on_hold |
| `dor_fulfilled` | boolean | BOOLEAN, default false | Ya | Status pemenuhan Definition of Ready proyek |

Aturan di basis data:

- `ck_projects_actual_after_start`: `actual_launch_date >= start_date`
- `ck_projects_priority_rank_min`: `priority_rank >= 1`
- `ck_projects_project_id_format`: `project_id ~ '^PRJ-[0-9]{3}$'`
- `ck_projects_status_valid`: `status IN ('planning', 'development', 'testing', 'released', 'on_hold')`
- `ck_projects_target_after_start`: `target_launch_date >= start_date`

### D-02 `resources`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `resource_id` (PK) | string | VARCHAR(20) | Ya | Format RES-001 |
| `resource_name` | string | VARCHAR(200) | Ya | Nama anggota tim |
| `primary_role_id` (FK ke `roles.role_id`) | string | VARCHAR(20) | Ya | Referensi ke roles.csv |
| `secondary_role_ids` | string | VARCHAR(200) | Tidak | Daftar role rangkap dipisah titik koma, contoh ROLE-DM;ROLE-FE |
| `cross_role_capable` | boolean | BOOLEAN, default false | Ya | Penanda kemampuan mengambil alih task lintas peran |
| `join_date` | date | DATE | Ya | Tanggal bergabung, menjadi dasar perhitungan masa onboarding |
| `seniority` | enum | VARCHAR(10) | Ya | junior, mid, senior |

Aturan di basis data:

- `ck_resources_resource_id_format`: `resource_id ~ '^RES-[0-9]{3}$'`
- `ck_resources_secondary_role_ids_format`: `secondary_role_ids ~ '^ROLE-[A-Z]+(;ROLE-[A-Z]+)*$'`
- `ck_resources_seniority_valid`: `seniority IN ('junior', 'mid', 'senior')`

### D-03 `roles`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `role_id` (PK) | string | VARCHAR(20) | Ya | ROLE-KAUR, ROLE-SA, ROLE-TW, ROLE-UIUX, ROLE-QA, ROLE-FE, ROLE-BE, ROLE-DM |
| `role_name` | string | VARCHAR(100) | Ya | Nama lengkap peran |
| `capacity_reference` | float | DOUBLE PRECISION, default 3.0 | Ya | Skor kapasitas referensi sebagai penyebut Resource Load Index, default 3.0 |
| `description` | string | TEXT | Tidak | Tanggung jawab utama peran |

Aturan di basis data:

- `ck_roles_capacity_reference_positive`: `capacity_reference > 0`
- `ck_roles_role_id_format`: `role_id ~ '^ROLE-[A-Z]+$'`

### D-04 `complexity_levels`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `complexity_id` (PK) | string | VARCHAR(20) | Ya | CX-VH, CX-H, CX-M, CX-L |
| `complexity_name` | string | VARCHAR(50) | Ya | Very High, High, Medium, Low |
| `min_days` | float | DOUBLE PRECISION | Ya | Batas bawah estimasi hari kerja |
| `max_days` | float | DOUBLE PRECISION | Ya | Batas atas estimasi hari kerja |
| `load_weight` | float | DOUBLE PRECISION | Ya | Bobot kontribusi terhadap Resource Load Index |

Aturan di basis data:

- `ck_complexity_levels_complexity_id_format`: `complexity_id ~ '^CX-[A-Z]+$'`
- `ck_complexity_levels_load_weight_min`: `load_weight >= 0`
- `ck_complexity_levels_max_days_after_min`: `max_days >= min_days`
- `ck_complexity_levels_min_days_min`: `min_days >= 0`

### D-05 `tasks`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `task_id` (PK) | string | VARCHAR(20) | Ya | Format TSK-0001 |
| `project_id` (FK ke `projects.project_id`) | string | VARCHAR(20) | Ya | Referensi ke projects.csv |
| `feature_name` | string | VARCHAR(200) | Ya | Nama fitur induk sebelum breakdown |
| `task_name` | string | VARCHAR(300) | Ya | Nama task hasil breakdown per role |
| `required_role_id` (FK ke `roles.role_id`) | string | VARCHAR(20) | Ya | Role yang dibutuhkan untuk mengerjakan task |
| `complexity_id` (FK ke `complexity_levels.complexity_id`) | string | VARCHAR(20) | Ya | Referensi ke complexity_levels.csv |
| `priority_rank` | integer | INTEGER | Ya | Angka 1 adalah prioritas tertinggi dalam proyek |
| `estimated_days` | float | DOUBLE PRECISION | Ya | Hasil kesepakatan estimasi bersama tim |
| `phase` | enum | VARCHAR(20) | Ya | planning, uiux, dm_dev, be_dev, fe_dev, testing, bugfix, documentation |
| `planned_start` | date | DATE | Ya | Rencana mulai, sudah mengecualikan hari libur |
| `planned_finish` | date | DATE | Ya | Rencana selesai |
| `actual_start` | date | DATE | Tidak | Kosong bila belum mulai |
| `actual_finish` | date | DATE | Tidak | Kosong bila belum selesai |
| `status` | enum | VARCHAR(20), default not_started | Ya | not_started, in_progress, blocked, on_hold, in_qa, done, dropped |
| `qa_reject_count` | integer | INTEGER, default 0 | Ya | Jumlah pengembalian dari QA ke FE, basis perhitungan rework |
| `dod_fulfilled` | boolean | BOOLEAN, default false | Ya | Status pemenuhan Definition of Done fitur |

Aturan di basis data:

- `ck_tasks_actual_finish_after_start`: `actual_finish >= actual_start`
- `ck_tasks_actual_finish_needs_start`: `actual_finish IS NULL OR actual_start IS NOT NULL`
- `ck_tasks_estimated_days_positive`: `estimated_days > 0`
- `ck_tasks_phase_valid`: `phase IN ('planning', 'uiux', 'dm_dev', 'be_dev', 'fe_dev', 'testing', 'bugfix', 'documentation')`
- `ck_tasks_planned_finish_after_start`: `planned_finish >= planned_start`
- `ck_tasks_priority_rank_min`: `priority_rank >= 1`
- `ck_tasks_qa_reject_count_min`: `qa_reject_count >= 0`
- `ck_tasks_status_valid`: `status IN ('not_started', 'in_progress', 'blocked', 'on_hold', 'in_qa', 'done', 'dropped')`
- `ck_tasks_task_id_format`: `task_id ~ '^TSK-[0-9]{4}$'`

### D-06 `task_dependencies`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `dependency_id` (PK) | string | VARCHAR(20) | Ya | Format DEP-001 |
| `task_id` (FK ke `tasks.task_id`) | string | VARCHAR(20) | Ya | Task yang bergantung |
| `depends_on_task_id` (FK ke `tasks.task_id`) | string | VARCHAR(20) | Ya | Task prasyarat |
| `dependency_type` | enum | VARCHAR(10) | Ya | hard untuk blokir total seperti BE menunggu DM, soft untuk pengerjaan parsial seperti FE membuat dummy tampilan |
| `propagation_factor` | float | DOUBLE PRECISION | Ya | 1.0 untuk hard, default 0.3 untuk soft |

Aturan di basis data:

- `ck_task_dependencies_dependency_id_format`: `dependency_id ~ '^DEP-[0-9]{3}$'`
- `ck_task_dependencies_dependency_type_valid`: `dependency_type IN ('hard', 'soft')`
- `ck_task_dependencies_hard_propagation_full`: `dependency_type <> 'hard' OR propagation_factor = 1.0`
- `ck_task_dependencies_no_self_dependency`: `task_id <> depends_on_task_id`
- `ck_task_dependencies_propagation_factor_range`: `propagation_factor > 0 AND propagation_factor <= 1`
- `uq_task_dependencies_task_id_depends_on_task_id`: kombinasi `task_id, depends_on_task_id` unik

### D-07 `assignments`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `assignment_id` (PK) | string | VARCHAR(20) | Ya | Format ASG-0001 |
| `task_id` (FK ke `tasks.task_id`) | string | VARCHAR(20) | Ya | Task yang ditugaskan |
| `resource_id` (FK ke `resources.resource_id`) | string | VARCHAR(20) | Ya | Resource pelaksana |
| `role_in_task` (FK ke `roles.role_id`) | string | VARCHAR(20) | Ya | Role yang dijalankan pada task ini, dapat berbeda dari primary role |
| `assigned_date` | date | DATE | Ya | Tanggal penugasan |
| `released_date` | date | DATE | Tidak | Tanggal lepas tugas, kosong bila masih aktif |
| `is_takeover` | boolean | BOOLEAN, default false | Ya | Penanda hasil pengalihan dari resource lain |

Aturan di basis data:

- `ck_assignments_assignment_id_format`: `assignment_id ~ '^ASG-[0-9]{4}$'`
- `ck_assignments_released_after_assigned`: `released_date >= assigned_date`

### D-08 `workload_items`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `item_id` (PK) | string | VARCHAR(20) | Ya | Format WLI-0001 |
| `resource_id` (FK ke `resources.resource_id`) | string | VARCHAR(20) | Ya | Resource penanggung jawab |
| `item_type` | enum | VARCHAR(20) | Ya | operational, ticket |
| `related_project_id` (FK ke `projects.project_id`) | string | VARCHAR(20) | Tidak | Aplikasi terkait, boleh kosong |
| `received_date` | date | DATE | Ya | Tanggal item masuk |
| `started_date` | date | DATE | Tidak | Tanggal mulai dikerjakan, merefleksikan aturan penundaan tiket pada FR-02.9 |
| `resolved_date` | date | DATE | Tidak | Tanggal selesai |
| `severity` | enum | VARCHAR(10) | Tidak | low, medium, high, critical |
| `is_hotfix` | boolean | BOOLEAN, default false | Ya | Penanda hotfix production yang memicu preemption |

Aturan di basis data:

- `ck_workload_items_item_id_format`: `item_id ~ '^WLI-[0-9]{4}$'`
- `ck_workload_items_item_type_valid`: `item_type IN ('operational', 'ticket')`
- `ck_workload_items_resolved_after_received`: `resolved_date >= received_date`
- `ck_workload_items_resolved_after_started`: `resolved_date >= started_date`
- `ck_workload_items_severity_valid`: `severity IN ('low', 'medium', 'high', 'critical')`
- `ck_workload_items_started_after_received`: `started_date >= received_date`

### D-09 `availability`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `availability_id` (PK) | string | VARCHAR(20) | Ya | Format AVL-001 |
| `resource_id` (FK ke `resources.resource_id`) | string | VARCHAR(20) | Ya | Resource terkait |
| `date_start` | date | DATE | Ya | Awal periode ketidakhadiran atau rotasi |
| `date_end` | date | DATE | Ya | Akhir periode |
| `absence_type` | enum | VARCHAR(20) | Ya | planned_leave, sudden_leave, maternity_leave, rotation_out, rotation_in |
| `is_known_at_planning` | boolean | BOOLEAN, default false | Ya | Penanda apakah sudah diketahui saat sprint planning |

Aturan di basis data:

- `ck_availability_absence_type_valid`: `absence_type IN ('planned_leave', 'sudden_leave', 'maternity_leave', 'rotation_out', 'rotation_in')`
- `ck_availability_availability_id_format`: `availability_id ~ '^AVL-[0-9]{3}$'`
- `ck_availability_date_end_after_start`: `date_end >= date_start`

### D-10 `change_events`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `event_id` (PK) | string | VARCHAR(20) | Ya | Format EVT-001 |
| `project_id` (FK ke `projects.project_id`) | string | VARCHAR(20) | Ya | Proyek terdampak |
| `event_type` | enum | VARCHAR(20) | Ya | change_request, priority_change, blocker, overrun, hotfix |
| `event_date` | date | DATE | Ya | Tanggal kejadian |
| `requested_by` | string | VARCHAR(100) | Tidak | Pemilik proses, Kaur, Asisten Manajer, atau System Analyst |
| `decision` | enum | VARCHAR(20) | Tidak | accept_now, defer_next, reject |
| `resolution_mode` | enum | VARCHAR(20) | Tidak | swap_task, extend_duration, scope_addition, reshuffle |
| `affected_task_id` (FK ke `tasks.task_id`) | string | VARCHAR(20) | Tidak | Task yang di-drop, ditunda, atau ditambahkan |
| `extension_days` | float | DOUBLE PRECISION | Tidak | Tambahan hari bila mode resolusi berupa perpanjangan durasi |

Aturan di basis data:

- `ck_change_events_decision_valid`: `decision IN ('accept_now', 'defer_next', 'reject')`
- `ck_change_events_event_id_format`: `event_id ~ '^EVT-[0-9]{3}$'`
- `ck_change_events_event_type_valid`: `event_type IN ('change_request', 'priority_change', 'blocker', 'overrun', 'hotfix')`
- `ck_change_events_extension_days_positive`: `extension_days > 0`
- `ck_change_events_resolution_mode_valid`: `resolution_mode IN ('swap_task', 'extend_duration', 'scope_addition', 'reshuffle')`

### D-11 `holidays`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `holiday_date` (PK) | date | DATE | Ya | Tanggal libur |
| `holiday_name` | string | VARCHAR(200) | Ya | Nama libur nasional atau cuti bersama |

## 7. Tabel milik J&C di luar Data Dictionary

Tabel pada bagian ini tidak termasuk final sources. J&C dapat mengubah strukturnya tanpa mengubah Data Dictionary.

### 7.1 Tabel yang dapat dibaca tWinner

| Objek | Isi | Jira |
|---|---|---|
| View Resource Load Index | Nilai RLI per anggota per minggu dari bobot task, beban non-proyek, dan kapasitas peran | DIG-187, DIG-192 |
| `resource_skills` | Tingkat penguasaan anggota per peran, termasuk lintas peran | DIG-63 |
| `change_event_details` | Persetujuan CR dan waktu selesai blocker, overrun, hotfix | DIG-63 |

### 7.2 Tabel internal J&C

Tabel berikut hanya dipakai aplikasi J&C dan tidak dibaca tWinner.

| Tabel | Isi | Jira |
|---|---|---|
| `staging_project_plan` | Baris mentah hasil unggah Project Plan sebelum validasi | DIG-113 |
| `import_job` | Catatan setiap impor: sumber, waktu, jumlah baris, status | DIG-113 |
| `staging_trello_action` | Riwayat aksi kartu Trello mentah | DIG-117 |
| `trello_list_mapping` | Pemetaan nama list Trello ke status dan phase task | DIG-117 |
| `staging_commit` | Riwayat commit TeamGit mentah | DIG-121 |
| `resource_alias` | Pemetaan identitas anggota di Trello, Git, dan Project Plan ke `resource_id` | DIG-110 |
| `event_log` | Event log untuk *process mining* | DIG-164 |
| `data_quality_result` | Hasil pemeriksaan kualitas data per aturan dan per sumber | DIG-145 |
| `rejected_row` | Baris yang ditolak beserta alasannya | DIG-145 |
| `audit_log` | Jejak perubahan data final sources: tabel, kunci, kolom, nilai lama, nilai baru, pengubah, waktu | DIG-63 |
| Tabel pengguna dan izin aplikasi | Akun dan peran aplikasi (RBAC), terpisah dari D-03 `roles` | DIG-17, DIG-18 |

### 7.3 Struktur `resource_skills` dan `change_event_details`

Kedua tabel ini menutup celah antara Data Dictionary dan kebutuhan fitur J&C (bagian 8). Keduanya menempel pada final sources lewat foreign key, sehingga isi D-02 dan D-10 tidak berubah.

**`resource_skills`** mencatat tingkat penguasaan setiap anggota pada peran yang dapat dijalankannya, termasuk peran rangkap dan kemampuan lintas peran. Satu baris mewakili satu pasangan anggota dan peran.

| Kolom | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|
| `resource_id` (PK, FK ke `resources.resource_id`) | VARCHAR(20) | Ya | Anggota tim |
| `role_id` (PK, FK ke `roles.role_id`) | VARCHAR(20) | Ya | Peran yang dikuasai |
| `proficiency_level` | SMALLINT | Ya | 1 = dasar, masih membutuhkan pendampingan; 2 = mandiri; 3 = mahir, dapat mengambil alih task dan membimbing anggota lain |
| `assessed_date` | DATE | Ya | Tanggal penilaian terakhir |

Aturan: `proficiency_level` bernilai 1 sampai 3. `primary_role_id` dan `secondary_role_ids` pada D-02 tetap menjadi sumber resmi daftar peran anggota, sedangkan `resource_skills` menambahkan tingkat penguasaannya serta peran lintas yang dapat diambil alih.

**`change_event_details`** melengkapi D-10 dengan persetujuan perubahan dan waktu selesai kejadian. Satu baris mewakili satu `event_id`.

| Kolom | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|
| `event_id` (PK, FK ke `change_events.event_id`) | VARCHAR(20) | Ya | Kejadian yang dilengkapi |
| `approved_by_resource_id` (FK ke `resources.resource_id`) | VARCHAR(20) | Tidak | Anggota yang menyetujui CR atau perubahan prioritas |
| `approved_date` | DATE | Tidak | Tanggal persetujuan |
| `resolved_date` | DATE | Tidak | Tanggal blocker, overrun, atau hotfix dinyatakan selesai; kosong bila masih berlangsung |

Aturan: `approved_date` dan `resolved_date` tidak boleh lebih awal dari `event_date` pada D-10. Validator J&C memeriksa aturan ini karena `event_date` berada di tabel lain.

## 8. Penyelesaian celah skema

J&C menerima Data Dictionary apa adanya sebagai final sources bersama. Kebutuhan J&C yang belum tertampung di Data Dictionary ditutup dengan tabel milik J&C berikut.

| Celah | Kebutuhan | Penyelesaian |
|---|---|---|
| Keahlian dan proficiency | F1 Master Data mencatat skill dan proficiency anggota, termasuk lintas peran. tWinner membutuhkannya untuk rekomendasi pengganti berbasis kapasitas dan skill. | Tabel `resource_skills` milik J&C, dapat dibaca tWinner. Istilah "keahlian" pada proposal merujuk ke tabel ini. |
| Waktu selesai blocker | D-10 hanya mencatat `event_date`, sehingga durasi blocker, overrun, dan hotfix tidak dapat dihitung. | Kolom `resolved_date` pada tabel `change_event_details`, dapat dibaca tWinner. |
| Approver CR | Berdasarkan wawancara dengan Tim DEVTI PuTI, CR dan perubahan prioritas disetujui Kaur atau Asisten Manajer setelah berdiskusi dengan System Analyst. D-10 hanya mencatat `requested_by` dan `decision`. | Kolom `approved_by_resource_id` dan `approved_date` pada tabel `change_event_details`. |
| Kolom audit | Jejak perubahan data dibutuhkan untuk karakteristik *traceability* ISO/IEC 25012. | Tabel `audit_log` internal J&C. D-01 sampai D-11 tidak mendapat kolom audit tambahan. |

## 9. Perubahan kontrak

1. Perubahan pada D-01 sampai D-11, termasuk penambahan kolom, nilai enum, atau format ID, dibuat melalui pull request yang berisi migrasi Alembic dan pembaruan dokumen ini. Sebelum pull request di-merge, perwakilan tWinner memberi konfirmasi tertulis di grup WhatsApp koordinasi J&C dan tWinner. J&C menyimpan tangkapan layar konfirmasi itu, beserta tanggal dan nama yang menyetujui, di issue Jira terkait. Approval di GitHub cukup dari anggota J&C sesuai `docs/PR_REVIEW.md`, sehingga anggota tWinner tidak perlu menjadi collaborator repository.
2. Perubahan pada tabel bagian 7.1 yang dibaca tWinner mengikuti prosedur yang sama.
3. Tabel internal J&C pada bagian 7.2 dapat diubah J&C tanpa persetujuan tWinner.
4. Setiap perubahan menaikkan nomor versi dan dicatat di riwayat versi.

## 10. Riwayat versi

| Versi | Perubahan |
|---|---|
| 1.0 | Versi awal. Persetujuan tWinner atas versi ini dicatat lewat konfirmasi WhatsApp di DIG-12. Isi: salinan Data Dictionary D-01 sampai D-11 sesuai migrasi DIG-15, pemilik dan hak akses, frekuensi pembaruan, aturan format, tabel pendukung J&C, penyelesaian celah skema (`resource_skills`, `change_event_details`, `audit_log`) |
