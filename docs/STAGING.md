# Staging untuk review PuTI (DIG-49)

Staging menjalankan susunan yang sama dengan `compose.prod.yaml` (docs/DEPLOYMENT.md) di satu
server, diperbarui otomatis setiap ada commit di `main` yang lulus CI, dan hanya berisi data
sintetis.

| Bagian | Jira | Status |
| --- | --- | --- |
| Server atau layanan cloud | DIG-204 | Menunggu keputusan tim |
| Deploy otomatis dari CI | DIG-205 | Workflow `Deploy staging` dan `ops/deploy/deploy.sh` siap; aktif setelah server diisi di pengaturan repository |
| HTTPS dan domain | DIG-206 | Setelah server ada |
| Data sintetis | DIG-49 | `python -m synthetic.load` |

## Kebutuhan server

- Linux 64-bit dengan Docker Engine dan plugin Compose v2, `git`, dan `curl`.
- Minimal 2 vCPU, 4 GB RAM, 20 GB disk (build image, PostgreSQL, backup 7 hari).
- Port 8080 (atau `WEB_PORT`) dapat dijangkau tim dan dosen, atau lewat reverse proxy HTTPS
  (DIG-206). Port PostgreSQL dan API tidak dibuka ke luar.
- Akses SSH untuk GitHub Actions (alamat IP runner GitHub berubah-ubah; bila SSH dibatasi per
  IP, gunakan VPN atau tunnel).

## Menyiapkan server (sekali)

```bash
sudo useradd --create-home --groups docker jc
sudo mkdir -p /opt/jc && sudo chown jc:jc /opt/jc
sudo -u jc git clone https://github.com/athalino-bakti/DIGITAL_TWIN.git /opt/jc
cd /opt/jc && sudo -u jc cp staging.env.example staging.env   # lalu isi nilainya
```

Repository privat: tambahkan *deploy key* hanya-baca di pengaturan repository dan clone lewat SSH.

Jalankan pertama kali dan isi data sintetis:

```bash
cd /opt/jc
docker compose -f compose.prod.yaml --env-file staging.env up -d --build
docker compose -f compose.prod.yaml --env-file staging.env exec api python -m synthetic.load
```

`synthetic.load` hanya mengisi basis data yang D-01 sampai D-11-nya masih kosong, menolak
`APP_ENV=production`, dan memasukkan semua tabel dalam satu transaksi. Hasilnya sama dengan
`python -m synthetic` seed 42 per 6 November 2026: 5 proyek, 13 anggota, 136 task, dan
seterusnya. Akun login dibuat dengan `create_user` dan `set_roles` (docs/DEPLOYMENT.md).

Pasang juga jadwal backup (docs/BACKUP.md) setelah PR backup masuk.

## Menghubungkan GitHub Actions

1. Di server, buat kunci SSH khusus deploy dan izinkan untuk user `jc`:

   ```bash
   sudo -u jc ssh-keygen -t ed25519 -N "" -f /home/jc/.ssh/github_deploy
   sudo -u jc sh -c 'cat /home/jc/.ssh/github_deploy.pub >> /home/jc/.ssh/authorized_keys'
   ```

2. Di GitHub: **Settings → Environments → New environment** bernama `staging`, lalu isi:

   | Jenis | Nama | Isi |
   | --- | --- | --- |
   | Secret | `STAGING_SSH_KEY` | Isi `/home/jc/.ssh/github_deploy` (kunci privat) |
   | Secret | `STAGING_SSH_KNOWN_HOSTS` | Hasil `ssh-keyscan -p <port> <host>` yang sudah dicocokkan dengan sidik jari server |
   | Variable | `STAGING_HOST` | Alamat server |
   | Variable | `STAGING_USER` | `jc` (bawaan) |
   | Variable | `STAGING_SSH_PORT` | `22` (bawaan) |
   | Variable | `STAGING_PATH` | `/opt/jc` (bawaan) |
   | Variable | `STAGING_URL` | Alamat staging yang dibuka tim, misalnya `https://staging.example` |

   `STAGING_HOST` boleh diisi di tingkat repository atau environment. Selama kosong, workflow
   hanya mencatat bahwa deploy dilewati dan tetap hijau.

3. Hapus kunci privat dari server setelah disalin ke GitHub:
   `sudo -u jc rm /home/jc/.ssh/github_deploy`.

4. Supaya deploy otomatis bisa ditahan, misalnya saat demo atau sesi review bersama PuTI:
   di environment `staging`, aktifkan **Required reviewers** dan pilih anggota tim. Setiap
   deploy lalu menunggu persetujuan di tab Actions; tanpa persetujuan, staging tetap di versi
   lama. Matikan lagi setelah demo bila deploy ingin kembali langsung jalan.

## Alur deploy

1. PR di-merge ke `main`; workflow `CI` berjalan.
2. Bila CI lulus, workflow `Deploy staging` masuk ke server lewat SSH dan menjalankan
   `ops/deploy/deploy.sh <commit>`.
3. Skrip mengambil commit itu, membuat backup (bila service backup sudah ada), menjalankan
   `docker compose up -d --build` (migrasi berjalan lebih dulu lewat container `migrate`), lalu
   menunggu `GET /api/v1/health/ready` sampai 2 menit. Commit yang aktif dicatat di `.deployed`.
4. Bila API tidak siap, workflow gagal dan log container ditampilkan.

Deploy manual: tab **Actions → Deploy staging → Run workflow**, atau di server
`sh ops/deploy/deploy.sh <commit>`.

Kembali ke versi sebelumnya: `sh ops/deploy/deploy.sh <commit lama>`. Migrasi tidak diturunkan
otomatis; bila commit lama memakai skema yang lebih lama, pulihkan backup sebelum deploy
(docs/BACKUP.md).
