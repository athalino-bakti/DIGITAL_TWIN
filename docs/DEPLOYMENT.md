# Image produksi dan menjalankannya (DIG-216)

J&C dikemas menjadi dua image:

| Image | Dockerfile | Isi |
| --- | --- | --- |
| `jc-api` | `backend/Dockerfile` | Python 3.11 slim, dependency persis dari `constraints.txt`, kode `app/`, migrasi Alembic. Berjalan sebagai user `jc` (uid 10001), satu worker uvicorn di port 8000. |
| `jc-web` | `frontend/Dockerfile` | Hasil `npm run build` yang disajikan `nginx-unprivileged` di port 8080 (tanpa root). nginx juga meneruskan `/api/` ke container API. |

`compose.prod.yaml` menjalankan keduanya bersama PostgreSQL 17 dan satu container `migrate`
yang menjalankan `alembic upgrade head` sebelum API dinyalakan. Workflow `Docker`
(`.github/workflows/docker.yml`) mem-build dan menguji susunan yang sama di setiap pull request
yang mengubah backend atau frontend.

Konfigurasi server staging (rahasia lewat `SECRETS_DIR`, domain, HTTPS, deploy dari CI,
backup) menyusul di DIG-204 s.d. DIG-206, DIG-217, dan DIG-218.

## Menjalankan di laptop

Butuh Docker Desktop. Dari folder repository (PowerShell):

```powershell
$env:POSTGRES_PASSWORD = "isi-password-database"
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose -f compose.prod.yaml up -d --build
```

Buka http://localhost:8080. Akun pertama dibuat dan diberi peran lewat CLI auth di dalam
container API (password diminta interaktif):

```powershell
docker compose -f compose.prod.yaml exec -it api python -m app.modules.auth.create_user --username bagas --full-name "Bagas Haris Saputro"
docker compose -f compose.prod.yaml exec api python -m app.modules.auth.set_roles --username bagas --role admin_it
```

Menghentikan: `docker compose -f compose.prod.yaml down`. Tambahkan `-v` untuk ikut menghapus
volume basis data.

## Variabel

| Variabel | Bawaan | Keterangan |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | wajib | Password pemilik basis data. Hindari karakter `@ : / ? #` karena disisipkan ke `DATABASE_URL`. |
| `JWT_SECRET_KEY` | wajib | Minimal 32 karakter. Nilai development ditolak karena `APP_ENV` bukan `development`. |
| `POSTGRES_USER`, `POSTGRES_DB` | `puti`, `digital_twin` | |
| `APP_ENV` | `staging` | `staging` atau `production`. Image tanpa compose memakai `production`. |
| `WEB_PORT` | `8080` | Port di host untuk frontend. |
| `IMAGE_TAG` | `local` | Tag image `jc-api` dan `jc-web`. |

API tidak membuka port ke host; semua request lewat nginx. Basis data juga hanya bisa dicapai
dari jaringan internal compose.

## Keputusan

- **Satu worker uvicorn.** Batas login gagal (`app/modules/auth/rate_limit.py`) disimpan di
  memori proses, jadi beberapa worker akan melipatgandakan batasnya. Untuk beban staging PuTI
  satu worker cukup.
- **Alamat IP klien.** nginx menimpa `X-Forwarded-For` dengan alamat yang ia lihat, dan uvicorn
  hanya mempercayai header itu dari subnet internal compose (`FORWARDED_ALLOW_IPS`). Dengan
  begitu klien tidak bisa memalsukan alamat untuk menghindari batas login per IP. Bila di depan
  nginx nanti ada reverse proxy TLS (DIG-206), alamat aslinya perlu diteruskan dengan modul
  `real_ip` nginx dari proxy itu saja.
- **Header keamanan dasar** (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
  dipasang di nginx; versi nginx tidak ditampilkan. CSP dan pemeriksaan OWASP di DIG-208.
- **Cache.** Berkas di `/assets/` bernama hash dan disimpan browser setahun; `index.html`
  selalu diperiksa ulang, jadi rilis baru langsung terpakai.
- **Migrasi terpisah dari API.** Container `migrate` berjalan sekali dan API baru dinyalakan
  bila migrasi berhasil, sehingga API tidak pernah melayani skema setengah jadi.
- **Pemilik basis data.** Di compose ini API memakai user pemilik basis data. Pemisahan ke role
  `jc_app` (docs/DATABASE_ROLES.md) dipasang bersama konfigurasi staging (DIG-217).
