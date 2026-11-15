# Pipeline impor terjadwal (DIG-28)

Job impor mengambil data dari sumber eksternal ke tabel staging, mencoba ulang bila gangguannya
sementara, mencatat setiap jalannya di tabel `import_job`, dan mengirim notifikasi bila gagal.

| Bagian | Jira | Berkas |
| --- | --- | --- |
| Penjadwalan, retry, CLI | DIG-127 | `backend/app/pipeline/runner.py`, `run.py`, `jobs.py` |
| Log terstruktur dan pemantauan | DIG-128 | `backend/app/pipeline/logging.py`, tabel `import_job`, `GET /api/v1/data/import-jobs` |
| Notifikasi kegagalan | DIG-129 | `backend/app/pipeline/notify.py` |

Sumber yang sudah ada jobnya: `trello` (Trello API, DIG-119). `project_plan` dan `teamgit` sudah
diizinkan di tabel `import_job`; jobnya didaftarkan di `JOBS` (`jobs.py`) begitu importernya
selesai (DIG-25, DIG-27).

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
6. Bila gagal: log level `ERROR` dan notifikasi webhook.

Impor Trello aman diulang: action yang sudah ada tidak ditulis dua kali (DIG-118), sehingga
jadwal yang tumpang tindih atau jalan ulang manual tidak menggandakan data.

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
- Basis data langsung:

```sql
SELECT job_id, source, status, attempts, started_at, finished_at, rows_written, error
FROM import_job
ORDER BY started_at DESC
LIMIT 20;
```

Log berformat JSON memuat `job_id`, `source`, `trigger`, `status`, `attempts`, `duration_ms`,
`rows_read`, `rows_written`, dan `error`, sehingga bisa disaring tanpa membaca teks bebas.
