# Digital Twin PuTI

Kerangka aplikasi dari referensi HTML Digital Twin PuTI. Branch `main` disiapkan sebagai fondasi bersama; isi modul dikembangkan terpisah pada branch fitur.

## Yang tersedia

- **React + TypeScript + Vite**: sidebar, header, routing Data / Digital Twin / Simulasi / Evaluasi, layout responsif, komponen placeholder, dan API client.
- **FastAPI**: konfigurasi environment, CORS, router modular, endpoint liveness dan readiness.
- **PostgreSQL**: Docker Compose, koneksi SQLAlchemy + psycopg, session dependency, dan konfigurasi Alembic.
- Tab Digital Twin: Timeline, Beban Resource, dan Dependency. Semua menampilkan keadaan kosong, tanpa angka dummy.

Belum ada autentikasi, unggah CSV, CRUD, tabel bisnis, Gantt, kalkulasi beban, graf dependency, mesin simulasi, evaluasi, atau ekspor. Identitas workspace bukan pengguna yang sudah login. Router modul masih kosong dan belum muncul di Swagger.

## Struktur

```text
frontend/src/
  app/                     # Layout, routing, navigasi bersama
  modules/
    data/
    digital-twin/
    simulasi/
    evaluasi/
  shared/                  # Komponen bersama dan API client
backend/
  app/
    api/                   # Router utama dan health check
    core/                  # Konfigurasi environment
    db/                    # Base SQLAlchemy dan session
    modules/               # Router kosong per modul
  migrations/              # Alembic, belum ada migrasi bisnis
  tests/
docs/
  BRANCH_WORKFLOW.md
compose.yaml               # PostgreSQL untuk development lokal
```

## Menjalankan lokal (PowerShell)

Prasyarat: Node.js 22.12+ (atau 24 LTS), Python 3.11+, Docker Desktop dengan Linux engine aktif. Jalankan perintah dari root repository kecuali disebutkan berbeda.

### 1. PostgreSQL

```powershell
Copy-Item .env.example .env
docker compose up -d db
docker compose ps
```

Database disimpan di named volume `postgres_data`. `docker compose down` menghentikan container tanpa menghapus data. Kredensial contoh hanya untuk lokal. Jika user/password/port di `.env` diubah, sesuaikan `DATABASE_URL` di `backend/.env` juga. PostgreSQL yang sudah diinisialisasi tidak mengganti kredensial hanya karena `.env` berubah.

### 2. Backend — terminal pertama

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Swagger: http://localhost:8000/docs
- Liveness: http://localhost:8000/api/v1/health
- Readiness PostgreSQL: http://localhost:8000/api/v1/health/ready

Liveness tetap `200` saat database belum aktif; readiness mengembalikan `503`. Indikator di footer frontend hanya memeriksa API, bukan readiness database. Backend tidak membuat tabel otomatis saat startup.

`constraints.txt` menyimpan versi dependency yang telah diuji. Perbarui file ini bersama perubahan dependency di `pyproject.toml`.

### 3. Frontend — terminal kedua

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Buka http://localhost:5173. Proxy Vite meneruskan `/api` ke `http://127.0.0.1:8000`. Tanpa backend, halaman tetap dapat dinavigasi dan footer menampilkan “API belum terhubung”. Klik “Coba lagi” setelah backend aktif. Font Google bersifat opsional; browser menggunakan font sistem jika offline.

Untuk macOS/Linux, gunakan `cp` dan `.venv/bin/python` sebagai pengganti `Copy-Item` dan `.\.venv\Scripts\python.exe`.

## Pemeriksaan

Dari `frontend/`:

```powershell
npm run build
```

Dari `backend/`:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m alembic heads
```

Tes health memakai dependency override untuk menguji status sukses/gagal tanpa PostgreSQL. Setelah database aktif, periksa koneksi nyata dengan `Invoke-RestMethod http://localhost:8000/api/v1/health/ready`. `alembic heads` belum menampilkan revisi karena belum ada skema bisnis.

## Migrasi saat modul mulai dibuat

Tambahkan model pada folder modul dan import model tersebut di `backend/migrations/env.py` agar Alembic mengenali metadata. Dari `backend/` dengan PostgreSQL aktif:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "create data module tables"
# Review isi migrasi sebelum diterapkan.
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Tidak ada model atau migrasi bisnis awal yang dipaksakan oleh scaffold ini. Detail pembagian pekerjaan: [alur branch](docs/BRANCH_WORKFLOW.md).

## Build frontend

`npm run build` menghasilkan `frontend/dist`. Hosting frontend perlu fallback ke `index.html` untuk deep link React Router. Proxy Vite hanya untuk development; saat deployment arahkan `/api` ke FastAPI melalui reverse proxy, atau set `VITE_API_BASE_URL` saat build dan sesuaikan `CORS_ORIGINS`. Compose saat ini hanya untuk database lokal.

Referensi teknis: [Vite](https://vite.dev/guide/), [router modular FastAPI](https://fastapi.tiangolo.com/tutorial/bigger-applications/), [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).
