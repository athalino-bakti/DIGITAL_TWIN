# Indeks dan pool koneksi PostgreSQL (DIG-210)

Hasil review indeks dan pengaturan koneksi basis data bersama J&C dan tWinner, per migrasi
`0026`. Tes `backend/tests/test_database_tuning.py` menjaga kesimpulan di dokumen ini tetap
berlaku.

## Indeks

### Query yang sering dipakai

Semua kolom yang dipakai untuk filter, join, atau urutan pada endpoint dan job utama sudah
punya indeks:

| Pemakai | Kolom yang dicari | Indeks |
| --- | --- | --- |
| Daftar task, Gantt, critical path | `tasks.project_id` | `ix_tasks_project_id` |
| Task saya, pengalihan task, heatmap | `assignments.task_id`, `assignments.resource_id` | indeks per kolom |
| Riwayat perubahan per task dan proyek | `change_events.affected_task_id`, `change_events.project_id` | indeks per kolom |
| Ketersediaan dan larangan periode bertumpuk | `availability (resource_id, daterange)` | GiST `ex_availability_no_overlap` |
| Beban non-proyek per anggota | `workload_items.resource_id` | indeks per kolom |
| Process map dan ekspor XES | `event_log (case_id, event_time)`, `(project_id, event_time)` | indeks gabungan |
| Pembentukan ulang event log | `event_log (source, source_ref)` | indeks gabungan |
| Riwayat kartu Trello | `staging_trello_action (card_id, action_date)` | indeks gabungan |
| Staging Project Plan per impor | `staging_project_plan (import_job_id, row_number)` | indeks gabungan |
| Laporan kualitas per impor | `data_quality_result (job_id, source, rule_id)`, `rejected_row (job_id, level)` | indeks gabungan |
| Jejak audit per entitas | `audit_log (entity, entity_id, occurred_at)` | indeks gabungan |
| Satu job impor berjalan per sumber | `import_job (source) WHERE status = 'running'` | indeks unik parsial |

### Foreign key tanpa indeks

PostgreSQL tidak membuat indeks otomatis untuk kolom foreign key. Ada tujuh kolom FK yang
sengaja dibiarkan tanpa indeks:

| Tabel | Kolom | Alasan |
| --- | --- | --- |
| `audit_log` | `actor_user_id` | Tidak dipakai untuk mencari; hanya diperiksa saat akun dihapus (`ON DELETE SET NULL`), yang jarang. |
| `event_log` | `resource_id` | Event log dibaca per case atau per proyek. Kolom ini hanya diperiksa saat data anggota dihapus (`ON DELETE SET NULL`), yang jarang karena anggota yang punya penugasan tidak bisa dihapus. |
| `resource_alias` | `mapped_by_user_id` | Hanya diperiksa saat akun dihapus. |
| `role_permission` | `permission_code` | Tabel referensi berisi puluhan baris. |
| `staging_trello_action` | `import_job_id` | Staging dibaca per kartu. Kolom ini hanya diperiksa saat job impor dihapus (`ON DELETE SET NULL`), dan aplikasi tidak menghapus job impor. |
| `task_manual_change` | `changed_by` | Hanya diperiksa saat akun dihapus. |
| `user_app_role` | `role_code` | Tabel kecil; kunci utama `(user_id, role_code)` sudah dipakai untuk mencari peran pengguna. |

Menambah indeks di kolom-kolom ini hanya memperberat penulisan (impor, ETL, audit) tanpa
mempercepat query yang ada. Bila kelak ada fitur yang mencari lewat salah satu kolom ini,
atau tabelnya tumbuh besar dan baris induknya sering dihapus, tambahkan indeks lewat migrasi
dan hapus barisnya dari `UNINDEXED_FK_ALLOWED`.

Tes `test_every_foreign_key_has_an_index_or_a_documented_reason` gagal bila ada FK baru
tanpa indeks yang belum diputuskan, atau bila pengecualian di atas sudah tidak diperlukan.

Untuk memeriksa ulang secara manual:

```sql
SELECT c.conrelid::regclass AS tabel, a.attname AS kolom_fk
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
  AND NOT EXISTS (SELECT 1 FROM pg_index i
                  WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]);
```

## Pool koneksi

API berjalan sebagai satu worker uvicorn (docs/DEPLOYMENT.md). Endpoint sinkron FastAPI
dijalankan di thread pool sampai 40 thread, dan setiap request memegang satu koneksi selama
berjalan. Karena PostgreSQL dipakai bersama tWinner (bawaan `max_connections` 100), API J&C
dibatasi sampai 10 koneksi; request berikutnya menunggu koneksi kosong, paling lama
`DB_POOL_TIMEOUT` detik.

| Variabel | Bawaan | Arti |
| --- | --- | --- |
| `DB_POOL_SIZE` | `5` | Koneksi yang dibiarkan terbuka |
| `DB_MAX_OVERFLOW` | `5` | Koneksi tambahan saat ramai, ditutup lagi setelah dipakai |
| `DB_POOL_TIMEOUT` | `10` | Detik menunggu koneksi kosong sebelum request gagal |
| `DB_POOL_RECYCLE` | `1800` | Detik sebelum koneksi dibuka ulang, menghindari koneksi basi |
| `DB_APPLICATION_NAME` | `jc-api` | Nama di `pg_stat_activity`, sehingga koneksi J&C dan tWinner mudah dibedakan |
| `DB_STATEMENT_TIMEOUT_MS` | `0` (tanpa batas); `30000` di service `api` | Query yang lebih lama dibatalkan PostgreSQL |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT_MS` | `0` (tanpa batas); `300000` di service `api` | Transaksi yang menganggur lebih lama diputus, sehingga lock tidak tertahan |

`pool_pre_ping` tetap aktif, sehingga koneksi yang terputus (misalnya setelah PostgreSQL
restart) diganti sebelum dipakai.

Batas waktu query sengaja hanya dipasang di service `api` pada `compose.prod.yaml`, bukan di
service `migrate`, karena migrasi pada tabel besar bisa sah berjalan lebih lama dari 30 detik.
Job satu kali yang dijalankan lewat service `api` (misalnya `exec api python -m synthetic.load`
di `ops/deploy/deploy.sh`) ikut memakai batas ini. Untuk job yang memang lama, lepaskan batasnya
saat menjalankan perintah, misalnya
`docker compose -f compose.prod.yaml run --rm -e DB_STATEMENT_TIMEOUT_MS=0 api python -m ...`.

Memantau koneksi yang sedang terbuka:

```sql
SELECT application_name, state, count(*)
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY 1, 2
ORDER BY 1, 2;
```
