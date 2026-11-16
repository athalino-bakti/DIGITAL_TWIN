# Backup PostgreSQL dan uji restore (DIG-218)

Skrip di `ops/backup/` dijalankan lewat service `backup` di `compose.prod.yaml` (image
`postgres:17-alpine`, versi `pg_dump` sama dengan server). Service ini tidak ikut
`docker compose up`; jadwalnya dipasang di host, sama seperti job impor (docs/IMPORT_PIPELINE.md).

| Skrip | Fungsi |
| --- | --- |
| `backup.sh` | `pg_dump` format custom ke `backups/daily/`, memeriksa isinya bisa dibaca, menyalin backup hari Minggu ke `backups/weekly/`, dan menghapus yang lama |
| `verify-restore.sh` | Memulihkan backup terbaru ke basis data sementara, membandingkannya dengan basis data asal, lalu menghapusnya |
| `restore.sh` | Memulihkan satu backup ke basis data **baru** untuk pemulihan sungguhan |

Workflow *Docker* menjalankan backup lalu `verify-restore.sh --strict` di setiap PR yang
mengubah backend atau frontend.

## Isi backup

- `jc_YYYYMMDD_HHMMSS.dump`: seluruh skema dan data basis data aplikasi, termasuk
  `alembic_version`. Dikompresi; dipulihkan dengan `pg_restore`.
- `jc_YYYYMMDD_HHMMSS.roles.sql`: role cluster (misalnya `jc_app`, docs/DATABASE_ROLES.md)
  **tanpa password**, karena role tidak ikut `pg_dump`. Password role diatur ulang saat server
  baru disiapkan.

Berkas dibuat dengan izin `600` di folder `700` karena berisi seluruh data, termasuk hash
password akun aplikasi. Folder `backups/` diabaikan git. Salin backup ke tempat lain di luar
server (penyimpanan kampus atau cloud) supaya tetap ada bila servernya rusak; cara dan tempatnya
diputuskan bersama server staging (DIG-204).

## Menjalankan manual

Dari folder repository di server, dengan variabel yang sama seperti saat `up`
(`POSTGRES_PASSWORD` dan lainnya, docs/DEPLOYMENT.md):

```bash
docker compose -f compose.prod.yaml run --rm backup
docker compose -f compose.prod.yaml run --rm --entrypoint sh backup /ops/verify-restore.sh
```

| Variabel | Bawaan | Keterangan |
| --- | --- | --- |
| `BACKUP_DIR` | `./backups` | Folder di host untuk hasil backup |
| `BACKUP_KEEP_DAILY` | `7` | Jumlah backup harian yang disimpan |
| `BACKUP_KEEP_WEEKLY` | `4` | Jumlah backup mingguan (hari Minggu) yang disimpan |

## Jadwal

Backup harian pukul 02.17 WIB dan uji restore setiap Senin pukul 03.17 WIB, di luar jam kerja
dan setelah job impor malam. Contoh cron di host (zona waktu server WIB):

```cron
17 2 * * * cd /opt/jc && docker compose -f compose.prod.yaml run --rm backup >> /var/log/jc/backup.log 2>&1
17 3 * * 1 cd /opt/jc && docker compose -f compose.prod.yaml run --rm --entrypoint sh backup /ops/verify-restore.sh >> /var/log/jc/backup.log 2>&1
```

Atau systemd timer, misalnya `/etc/systemd/system/jc-backup.service`:

```ini
[Unit]
Description=Backup basis data J&C

[Service]
Type=oneshot
WorkingDirectory=/opt/jc
EnvironmentFile=/opt/jc/staging.env
ExecStart=/usr/bin/docker compose -f compose.prod.yaml run --rm backup
```

dan `/etc/systemd/system/jc-backup.timer`:

```ini
[Unit]
Description=Jadwal backup J&C

[Timer]
OnCalendar=*-*-* 02:17:00
Persistent=true

[Install]
WantedBy=timers.target
```

Kode keluar bukan 0 berarti gagal; pasang pemantauan pada log atau status timer. Notifikasi ke
kanal tim bisa memakai webhook yang sama dengan job impor (`NOTIFY_WEBHOOK_URL`, PR #34).

## Uji restore

`verify-restore.sh` gagal (kode 1) bila:

- `pg_restore` error (misalnya berkas terpotong atau rusak);
- versi migrasi (`alembic_version`) hasil restore berbeda dengan asal;
- ada tabel asal yang tidak ada di hasil restore;
- tabel yang berisi data di asal kosong setelah dipulihkan.

Selisih jumlah baris lain hanya diperingatkan, karena data bisa berubah antara backup dan uji.
Dengan `--strict` semua selisih dianggap gagal; dipakai di CI, saat tidak ada yang menulis.

## Memulihkan

1. Pilih berkas, biasanya backup terbaru di `backups/daily/`.
2. Pulihkan ke basis data **baru**. Skrip menolak nama basis data yang sudah ada, supaya data
   yang sedang dipakai tidak tertimpa tanpa sengaja:

   ```bash
   docker compose -f compose.prod.yaml run --rm --entrypoint sh backup \
     /ops/restore.sh /backups/daily/jc_20261116_021700.dump digital_twin_pulih
   ```

3. Periksa hasilnya, misalnya `python -m app.qa.schema_check` dengan `DATABASE_URL` ke basis
   data baru, dan cek data penting di aplikasi.
4. Hentikan API (`docker compose -f compose.prod.yaml stop api web`), lalu ganti nama:

   ```bash
   docker compose -f compose.prod.yaml exec db psql -U puti -d postgres \
     -c "ALTER DATABASE digital_twin RENAME TO digital_twin_rusak" \
     -c "ALTER DATABASE digital_twin_pulih RENAME TO digital_twin"
   docker compose -f compose.prod.yaml up -d
   ```

5. Simpan `digital_twin_rusak` sampai yakin pemulihan benar, baru hapus.

Di server baru, role dari berkas `.roles.sql` dibuat otomatis oleh `restore.sh` sebelum data
dipulihkan; password `jc_app` diatur ulang sesuai docs/DATABASE_ROLES.md.

Uji lokal 16 November 2026 (PostgreSQL 16): backup, uji restore ketat, peringatan saat data
berubah, gagal saat tabel kosong atau berkas terpotong, penolakan restore ke basis data yang
sudah ada, dan rotasi (tersisa 3 dari 6 backup dengan `BACKUP_KEEP_DAILY=3`) berjalan sesuai.
