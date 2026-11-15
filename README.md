# Digital Twin PuTI

Kerangka aplikasi dari referensi HTML Digital Twin PuTI. Branch `main` disiapkan sebagai fondasi bersama; isi modul dikembangkan terpisah pada branch fitur.

## Yang tersedia

- **React + TypeScript + Vite**: sidebar, header, routing Data / Digital Twin / Simulasi / Evaluasi, layout responsif, komponen placeholder, dan API client.
- **FastAPI**: konfigurasi environment, CORS, router modular, endpoint liveness dan readiness.
- **PostgreSQL**: Docker Compose, koneksi SQLAlchemy + psycopg, session dependency, dan konfigurasi Alembic.
- Tab Digital Twin: Timeline, Beban Resource, dan Dependency. Semua menampilkan keadaan kosong, tanpa angka dummy.

Belum ada autentikasi, unggah CSV, CRUD, Gantt, kalkulasi beban, graf dependency, mesin simulasi, evaluasi, atau ekspor. Identitas workspace bukan pengguna yang sudah login. Router modul masih kosong dan belum muncul di Swagger.

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
  migrations/              # Alembic: skema final sources D-01 s.d. D-11
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

Tes health memakai dependency override untuk menguji status sukses/gagal tanpa PostgreSQL. Setelah database aktif, periksa koneksi nyata dengan `Invoke-RestMethod http://localhost:8000/api/v1/health/ready`. `alembic heads` harus menampilkan tepat satu revisi.

### Skema basis data vs Data Dictionary

Dari `backend/`, setelah `alembic upgrade head`:

```powershell
.\.venv\Scripts\python.exe -m app.qa.schema_check
```

Script ini membandingkan tabel D-01 sampai D-11 di basis data dengan bagian 6 `docs/DATA_CONTRACT.md`: daftar kolom, tipe, wajib/boleh kosong, default, primary key, foreign key, serta nama aturan `ck_`, `uq_`, dan `ex_` dua arah. Hasilnya `Cocok: ...` (kode keluar 0) atau daftar selisih (kode keluar 1). Tes `tests/test_schema_check.py` menjalankan pemeriksaan yang sama di CI, jadi migrasi yang mengubah tabel Data Dictionary harus disertai pembaruan DATA_CONTRACT di pull request yang sama, dan sebaliknya.

## Migrasi saat modul mulai dibuat

Tambahkan model pada folder modul dan import model tersebut di `backend/migrations/env.py` agar Alembic mengenali metadata. Dari `backend/` dengan PostgreSQL aktif:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "create data module tables"
# Review isi migrasi sebelum diterapkan.
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Model final sources D-01 s.d. D-11 (Data Dictionary bersama tWinner) ada di `backend/app/modules/data/models.py`, dengan nilai enum dan format ID di `enums.py`. Enum disimpan sebagai VARCHAR + CHECK constraint, bukan tipe ENUM PostgreSQL. Nama constraint mengikuti konvensi di `app/db/base.py` (`pk_`, `fk_`, `ix_`, `uq_`, `ck_`). Detail pembagian pekerjaan: [alur branch](docs/BRANCH_WORKFLOW.md).

### Tes migrasi naik dan turun

`tests/test_migrations.py` menguji setiap migrasi terhadap PostgreSQL sungguhan:

| Tes | Yang dicek |
| --- | --- |
| `test_only_one_head` | Hanya ada satu head migrasi |
| `test_upgrade_downgrade_upgrade` | `upgrade head` → `downgrade base` → `upgrade head` berhasil, dan setelah downgrade tidak tersisa tabel, view, sequence, atau enum |
| `test_each_revision_can_step_down_and_up` | Setiap revisi bisa naik, turun satu langkah, lalu naik lagi |
| `test_models_match_migrations` | Model SQLAlchemy sama dengan skema hasil migrasi (`alembic check`) |

Tes ini **menghapus seluruh isi** database tujuan, jadi hanya berjalan jika `MIGRATION_TEST_DATABASE_URL` diisi dan nama database berakhiran `_test`. Tanpa variabel itu, tes dilewati dan `pytest` biasa tetap tidak butuh database. Di GitHub Actions, job **Migrasi (alembic naik-turun)** menjalankannya otomatis dengan PostgreSQL 17.

Menjalankan lokal dari `backend/` dengan container database aktif:

```powershell
docker compose exec db createdb -U puti digital_twin_test   # cukup sekali
$env:MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://puti:puti_local@localhost:5432/digital_twin_test"
.\.venv\Scripts\python.exe -m pytest -m migration -v
```

Saat menulis migrasi, pastikan `downgrade()` membalik `upgrade()` sepenuhnya, termasuk `DROP TYPE` untuk enum PostgreSQL (`sa.Enum(name="...").drop(op.get_bind())`).

### Tes API dengan PostgreSQL

Tes endpoint yang butuh database sungguhan (misalnya `tests/test_projects_api.py`) memakai marker `db` dan variabel `TEST_DATABASE_URL`, dengan aturan nama `_test` yang sama. Job **Migrasi (alembic naik-turun)** juga menjalankannya.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://puti:puti_local@localhost:5432/digital_twin_test"
.\.venv\Scripts\python.exe -m pytest -m db -v
```

## Build frontend

`npm run build` menghasilkan `frontend/dist`. Hosting frontend perlu fallback ke `index.html` untuk deep link React Router. Proxy Vite hanya untuk development; saat deployment arahkan `/api` ke FastAPI melalui reverse proxy, atau set `VITE_API_BASE_URL` saat build dan sesuaikan `CORS_ORIGINS`. Compose saat ini hanya untuk database lokal.

## Data sintetis

Selama data PuTI belum tersedia, `python -m synthetic` dari folder `backend/` menghasilkan final sources D-01 s.d. D-11, sumber mentah (Project Plan, Trello, git log), dan data kotor untuk pengujian. Detail: [generator data sintetis](docs/SYNTHETIC_DATA.md).

Referensi teknis: [Vite](https://vite.dev/guide/), [router modular FastAPI](https://fastapi.tiangolo.com/tutorial/bigger-applications/), [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).

## Login dan sesi pengguna

Backend menyediakan login berbasis token (JWT). Belum ada halaman kelola akun sampai RBAC (DIG-18), jadi akun dibuat dari terminal, dari folder `backend` dengan venv aktif:

```powershell
python -m app.modules.auth.create_user --username bagas --full-name "Bagas Haris Saputro"
# opsional: --resource-id RES-001 untuk menautkan akun ke anggota tim
```

Password diminta lewat prompt, minimal 8 karakter, dan disimpan sebagai hash scrypt.

Akun baru belum punya peran aplikasi, jadi belum bisa membuka endpoint yang dilindungi izin. Beri peran lewat `set_roles`, lihat bagian [Peran aplikasi dan izin (RBAC)](#peran-aplikasi-dan-izin-rbac).

| Endpoint | Body / header | Respons |
| --- | --- | --- |
| `POST /api/v1/auth/login` | `{"username": "...", "password": "..."}` | `200` `{access_token, token_type: "bearer", expires_in, user}` · `401` username atau password salah · `422` body tidak valid |
| `GET /api/v1/auth/me` | `Authorization: Bearer <access_token>` | `200` data user · `401` token tidak ada, rusak, kedaluwarsa, atau akun nonaktif |

- Username tidak peka huruf besar/kecil dan spasi di ujung diabaikan.
- Username salah, password salah, dan akun nonaktif mendapat pesan yang sama agar tidak membocorkan akun mana yang terdaftar.
- Token berlaku `ACCESS_TOKEN_EXPIRE_MINUTES` menit (default 60). Saat API membalas `401`, frontend sebaiknya menghapus token dan mengarahkan ke halaman login.
- Endpoint lain bisa mewajibkan login dengan dependency `CurrentUser` dari `app.modules.auth.dependencies`.
- `JWT_SECRET_KEY` wajib diganti di luar development (`APP_ENV=staging`/`production`); aplikasi menolak start bila masih memakai nilai bawaan.

### Peran aplikasi dan izin (RBAC)

Satu pengguna boleh punya banyak peran aplikasi; izinnya gabungan dari semua perannya. Peran ini terpisah dari D-03 `roles` (peran kerja di PuTI). Matriks di bawah mengikuti Tabel 2.1 dan 2.2 (FR-01 sampai FR-12) dokumen Rancangan Kebutuhan dan Arsitektur. Perubahan matriks dilakukan lewat migrasi baru.

| Izin | `kaur_asman` | `system_analyst` | `anggota_tim` | `admin_data` | `admin_it` |
| --- | :-: | :-: | :-: | :-: | :-: |
| `master_data:read` | ✓ | ✓ | ✓ | ✓ |  |
| `master_data:write` |  |  |  | ✓ |  |
| `import:run` |  |  |  | ✓ |  |
| `data_quality:read` |  | ✓ |  | ✓ |  |
| `change_event:write` (FR-05, semua task) | ✓ | ✓ |  |  |  |
| `change_event:write_own` (FR-05, task miliknya) |  |  | ✓ |  |  |
| `availability:write` (FR-06) | ✓ | ✓ |  |  |  |
| `baseline:read` (FR-08 s.d. FR-11) | ✓ | ✓ |  |  |  |
| `workload:read_all` | ✓ | ✓ |  |  |  |
| `workload:read_own` | ✓ | ✓ | ✓ |  |  |
| `event_log:export` (FR-07) |  |  |  | ✓ |  |
| `user:manage` |  |  |  |  | ✓ |

- System Analyst yang juga menjalankan tugas Administrator Data (Tabel 2.1) cukup diberi dua peran: `system_analyst` dan `admin_data`.
- `change_event:write_own` dan `workload:read_own` hanya membuka endpoint; pembatasan ke task atau data milik pengguna sendiri dicek di endpoint tersebut.

Mengatur peran dari folder `backend` (belum ada halaman kelola akun):

```powershell
python -m app.modules.auth.set_roles --list
python -m app.modules.auth.set_roles --username bagas --role admin_data --role system_analyst
```

- `GET /api/v1/auth/me` dan respons login memuat `roles` dan `permissions`; frontend memakai `permissions` untuk menyembunyikan menu dan tombol (DIG-92).
- Endpoint dilindungi dengan `Depends(require_permission(Perm.MASTER_DATA_WRITE))` dari `app.modules.auth.dependencies`. Tanpa token: `401`. Login tapi tidak berizin: `403`.
- Izin dibaca ulang di setiap request, jadi perubahan peran langsung berlaku tanpa login ulang.
