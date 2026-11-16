# Pipeline impor terjadwal (DIG-28)

Job impor mengambil data dari sumber eksternal ke tabel staging, mencoba ulang bila gangguannya
sementara, mencatat setiap jalannya di tabel `import_job`, dan mengirim notifikasi bila gagal.

| Bagian | Jira | Berkas |
| --- | --- | --- |
| Penjadwalan, retry, CLI | DIG-127 | `backend/app/pipeline/runner.py`, `run.py`, `jobs.py` |
| Log terstruktur dan pemantauan | DIG-128 | `backend/app/pipeline/logging.py`, tabel `import_job`, `GET /api/v1/data/import-jobs` |
| Notifikasi kegagalan | DIG-129 | `backend/app/pipeline/notify.py` |

Sumber yang sudah ada jobnya:

- `trello` (Trello API, DIG-119): terjadwal, terdaftar di `JOBS` (`jobs.py`).
- `project_plan` (DIG-25): unggah manual lewat `POST /api/v1/data/imports/project-plan`. Tidak
  ada sumber yang bisa ditarik terjadwal, jadi tidak terdaftar di `JOBS`; endpoint memanggil
  `run_job("project_plan", job_fn=...)` dengan isi berkas yang sudah diterima. Lihat bagian
  [Unggah Project Plan](#unggah-project-plan-dig-25).
- `teamgit` sudah diizinkan di tabel `import_job`; jobnya didaftarkan di `JOBS` begitu
  importernya selesai (DIG-27).

Setiap baris staging menunjuk job yang menulisnya lewat kolom `import_job_id` (DIG-113):

| Tabel | `import_job_id` | Bila job dihapus |
| --- | --- | --- |
| `staging_project_plan` | wajib; satu unggahan = satu batch | barisnya ikut terhapus (CASCADE) |
| `staging_trello_action` | job pertama yang menyimpan action; kosong untuk baris sebelum DIG-113 | action tetap, kolomnya dikosongkan (SET NULL) |

## Menjalankan manual

Dari folder `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.pipeline.run trello
```

| Kode keluar | Arti |
| --- | --- |
| `0` | Berhasil |
| `1` | Gagal setelah semua percobaan; detail ada di `import_job.error` dan log |
| `2` | Job sumber yang sama masih berjalan, job baru tidak dimulai |

## Alur satu job

1. Job `running` dari sumber yang sama yang lebih tua dari `IMPORT_STALE_MINUTES` ditutup
   `failed` (prosesnya kemungkinan mati di tengah jalan, misalnya server restart).
2. Baris baru `running` dibuat. Index unik parsial `uq_import_job_one_running_per_source`
   menjamin hanya satu job per sumber yang berjalan, termasuk bila cron dan admin memicu
   bersamaan.
3. Job dijalankan dalam satu transaksi dan menerima `job_id` baris tersebut (sama di setiap
   percobaan), untuk diisikan ke kolom `import_job_id` di tabel staging (DIG-113). Bila gagal,
   transaksi di-rollback sehingga staging tidak setengah terisi dan tidak ada baris staging
   yang menunjuk job gagal.
4. Error sementara (jaringan putus, timeout, Trello 429/5xx, koneksi basis data putus) dicoba
   ulang sampai `IMPORT_MAX_ATTEMPTS` kali dengan jeda `IMPORT_RETRY_DELAY_SECONDS`, lalu dua
   kali lipat di setiap percobaan berikutnya (60 s, 120 s, ...). Error permanen (kredensial
   ditolak, papan tidak ada, konektor nonaktif, konfigurasi kosong) langsung gagal.
5. Baris job ditutup `succeeded` atau `failed` dengan jumlah percobaan, baris dibaca/ditulis,
   rincian per papan, dan pesan error. Token dan URL webhook disamarkan menjadi `***`.
   Penutupan ini hanya berlaku bila baris masih `running`: job sah yang berjalan lebih lama
   dari `IMPORT_STALE_MINUTES` dan sudah ditutup `failed` oleh job berikutnya tidak ditimpa,
   melainkan memicu log WARNING dan notifikasi agar batasnya dinaikkan.
6. Bila gagal: log level `ERROR` dan notifikasi webhook.

Pilih `IMPORT_STALE_MINUTES` jauh di atas durasi job terlama. Job yang prosesnya mati baru
ditutup saat job sumber yang sama berikutnya dimulai; sampai saat itu endpoint pemantauan
menandainya `stale: true`.

Impor Trello aman diulang: action yang sudah ada tidak ditulis dua kali (DIG-118), sehingga
jadwal yang tumpang tindih atau jalan ulang manual tidak menggandakan data.

## Unggah Project Plan (DIG-25)

`POST /api/v1/data/imports/project-plan`, `multipart/form-data`, izin `import:run`
(Administrator Data).

| Field | Keterangan |
| --- | --- |
| `file` | `.csv` (UTF-8, pemisah `,` atau `;`) atau `.xlsx`, paling besar 5 MB dan 10.000 baris data |
| `project_id` | `PRJ-xxx`; kosong = diambil dari nama berkas `project_plan_PRJ-xxx` |
| `dry_run` | bawaan `true`: pratinjau saja, tanpa job dan tanpa menulis staging |
| `sheet` | sheet XLSX; kosong = sheet pertama |
| `column_map` | JSON `{"judul kolom": "atribut" atau null}` yang menimpa pemetaan bawaan |

Alur:

1. Pratinjau (`dry_run=true`) menampilkan pemetaan kolom, kolom yang tidak terpetakan, kolom
   wajib yang hilang, 20 baris pertama, dan masalah struktur. Bila berkas identik dengan impor
   sukses terakhir proyek itu, `same_file_job_id` terisi sebagai peringatan.
2. Impor (`dry_run=false`) menjalankan job `project_plan` dengan satu percobaan dan tanpa
   notifikasi webhook (pengunggah melihat hasilnya langsung). Berkas yang strukturnya rusak
   tetap tercatat sebagai job `failed` dan dibalas 422 beserta `job_id`.
3. Setiap unggahan menjadi batch baru di `staging_project_plan`. ETL DIG-29 memakai job sukses
   terakhir per `project_id`.

Nilai sel disimpan apa adanya sebagai teks; normalisasi tanggal, status, dan PIC ada di DIG-29,
validasi di DIG-31. Sel XLSX bertipe tanggal ditulis ISO (`2026-09-14`) dan angka dengan titik
desimal; jumlahnya per kolom ada di `typed_cells`.

## Konfigurasi

| Variabel | Bawaan | Keterangan |
| --- | --- | --- |
| `TRELLO_BOARD_IDS` | kosong | Papan yang diimpor, dipisah koma (shortLink atau id). Butuh juga `TRELLO_API_ENABLED=true`, `TRELLO_API_KEY`, `TRELLO_API_TOKEN`. |
| `IMPORT_MAX_ATTEMPTS` | `3` | Percobaan per job (1 s.d. 10) |
| `IMPORT_RETRY_DELAY_SECONDS` | `60` | Jeda sebelum percobaan kedua |
| `IMPORT_STALE_MINUTES` | `120` | Batas job `running` dianggap macet |
| `LOG_FORMAT` | `text` | `json` untuk satu objek JSON per baris (disarankan di server) |
| `LOG_LEVEL` | `INFO` | |
| `NOTIFY_WEBHOOK_URL` | kosong | **Rahasia.** Incoming webhook Slack, Discord, Google Chat, atau Mattermost. Kosong = tanpa notifikasi. |
| `NOTIFY_TIMEOUT_SECONDS` | `10` | |

Payload notifikasi berisi `text` dan `content` sekaligus, jadi satu URL dari layanan mana pun di
atas cukup. Pesan dipotong 1800 karakter. Gagal mengirim notifikasi hanya dicatat sebagai
warning dan tidak mengubah status job.

## Menjadwalkan di server (staging, DIG-49)

Jadwal belum ditetapkan; contoh di bawah menjalankan impor Trello tiap jam pada menit ke-17.
Pakai `--trigger schedule` agar di `import_job` terlihat bedanya dengan jalan manual.

### cron

```cron
17 * * * * cd /opt/jc/backend && .venv/bin/python -m app.pipeline.run trello --trigger schedule >> /var/log/jc/import.log 2>&1
```

### systemd timer

`/etc/systemd/system/jc-import-trello.service`:

```ini
[Unit]
Description=Impor Trello J&C

[Service]
Type=oneshot
User=jc
WorkingDirectory=/opt/jc/backend
Environment=LOG_FORMAT=json SECRETS_DIR=/run/secrets/jc
ExecStart=/opt/jc/backend/.venv/bin/python -m app.pipeline.run trello --trigger schedule
```

`/etc/systemd/system/jc-import-trello.timer`:

```ini
[Unit]
Description=Jadwal impor Trello J&C

[Timer]
OnCalendar=*-*-* *:17:00
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
```

Aktifkan dengan `systemctl enable --now jc-import-trello.timer`; log dibaca dengan
`journalctl -u jc-import-trello`.

## Memantau

- `GET /api/v1/data/import-jobs?source=trello&status=failed&limit=20`: riwayat job terbaru
  lebih dulu. Izin `data_quality:read` (System Analyst, admin data, admin IT).
- `GET /api/v1/data/import-jobs/{job_id}`: satu job beserta `details` per papan (action dibaca,
  ditulis, sudah ada, dilewati per alasan).
- Field `stale` bernilai `true` untuk job yang masih `running` tetapi sudah lebih lama dari
  `IMPORT_STALE_MINUTES`: prosesnya kemungkinan mati dan perlu dicek.
- Basis data langsung:

```sql
SELECT job_id, source, status, attempts, started_at, finished_at, rows_written, error
FROM import_job
ORDER BY started_at DESC
LIMIT 20;
```

Log berformat JSON memuat `job_id`, `source`, `trigger`, `status`, `attempts`, `duration_ms`,
`rows_read`, `rows_written`, dan `error`, sehingga bisa disaring tanpa membaca teks bebas.

Logger `httpx` dan `httpcore` dibatasi ke WARNING berapa pun `LOG_LEVEL`-nya, karena di level
INFO keduanya mencatat URL setiap request, termasuk URL webhook notifikasi yang rahasia.
