# Pengembangan per branch

## Batas isi main

Untuk tahap awal, `main` hanya berisi fondasi bersama: layout, navigasi, halaman placeholder, API client, konfigurasi backend, router kosong, koneksi PostgreSQL, Alembic, dan dokumentasi. Implementasi modul dikerjakan pada branch fitur. Branch di bawah adalah rencana; scaffold tidak otomatis membuat branch, commit, atau push.

| Branch | Frontend | Backend | Cakupan nanti |
| --- | --- | --- | --- |
| `feature/data` | `frontend/src/modules/data/` | `backend/app/modules/data/` | Import CSV, validasi, master data, model dasar |
| `feature/digital-twin` | `frontend/src/modules/digital-twin/` | `backend/app/modules/digital_twin/` | Baseline, timeline, beban resource, dependency |
| `feature/simulasi` | `frontend/src/modules/simulasi/` | `backend/app/modules/simulasi/` | Parameter, skenario, eksekusi simulasi |
| `feature/evaluasi` | `frontend/src/modules/evaluasi/` | `backend/app/modules/evaluasi/` | Perbandingan baseline dan hasil, indikator evaluasi |

Nama modul mengikuti navigasi referensi HTML. Referensi memberikan detail Data dan Digital Twin; cakupan Simulasi dan Evaluasi masih garis besar untuk disepakati saat implementasi.

## Memulai dari scaffold

Setelah scaffold direview, simpan sebagai commit awal pada `main`:

```powershell
git add .
git commit -m "chore: scaffold React FastAPI PostgreSQL"
git switch -c feature/data
```

Untuk memulai modul lain dari fondasi yang sama, pastikan perubahan branch sebelumnya sudah disimpan:

```powershell
git switch main
git switch -c feature/digital-twin
```

Gunakan pola yang sama untuk `feature/simulasi` dan `feature/evaluasi`. Jangan memasukkan isi modul ke `main` selama tahap kerangka. Saat integrasi mulai diinginkan, gabungkan modul yang sudah selesai melalui review. Jika `main` perlu tetap murni kerangka, buat branch `integration` dari `main` sebagai tempat penggabungan modul.

## Konvensi implementasi

1. Simpan halaman, komponen, dan API modul di folder frontend modulnya. Pindahkan ke `shared/` hanya jika benar-benar dipakai bersama.
2. Tambahkan `schemas.py`, `service.py`, `models.py`, dan endpoint pada folder backend modul saat dibutuhkan. Router dasar sudah terhubung lewat `app/api/router.py`.
3. Gunakan `Depends(get_db)` dari `app/db/session.py` untuk session database. Transaksi/commit dilakukan eksplisit di service; dependency tidak melakukan commit otomatis.
4. Prefix API: `/api/v1/data`, `/api/v1/digital-twin`, `/api/v1/simulasi`, `/api/v1/evaluasi`. Kontrak endpoint bisnis baru ditentukan pada branch fitur, bukan melalui endpoint dummy di main.
5. Tabel bisnis dibuat melalui Alembic. Import model ke `migrations/env.py` dan sertakan migrasi dalam branch pemilik model tersebut.
6. Sepakati kontrak data antarmodul sebelum integrasi. Digital Twin memerlukan data dasar; Simulasi memerlukan baseline; Evaluasi memerlukan hasil simulasi. Jangan menggandakan model yang sama pada branch berbeda.
7. Saat migrasi dari beberapa branch digabung, periksa `alembic heads`. Jika muncul beberapa head, review relasi migrasi lalu buat merge revision yang sesuai sebelum `upgrade head`.
8. Jalankan build frontend, lint dan tes backend sebelum review. Tambahkan tes perilaku bisnis saat modulnya diimplementasikan.

Perubahan fondasi yang dibutuhkan beberapa modul sebaiknya dibuat terpisah dan diintegrasikan lebih dulu agar konflik pada router, konfigurasi, dan komponen bersama tetap kecil.
