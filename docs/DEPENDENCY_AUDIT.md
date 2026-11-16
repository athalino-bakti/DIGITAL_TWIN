# Audit dependency (DIG-209)

Workflow `.github/workflows/dependency-audit.yml` mencari celah keamanan yang sudah diumumkan
(CVE, GHSA, PYSEC) pada library yang dipakai backend dan frontend. Workflow jalan di setiap pull
request, setelah merge ke `main`, setiap Senin pagi, dan bisa dijalankan manual dari tab
*Actions*. Jadwal mingguan perlu karena celah baru bisa diumumkan untuk versi yang sudah lama
dipakai, tanpa ada perubahan kode.

| Job | Alat | Yang diperiksa | Gagal bila |
| --- | --- | --- | --- |
| Audit Python | `pip-audit` 2.10.1 (basis data PyPI/OSV) | Semua versi di `backend/constraints.txt`, ditambah paket yang terpasang di Linux tetapi tidak ada di constraints (misalnya `uvloop`) | Ada celah apa pun |
| Audit Node | `npm audit` | Semua paket di `frontend/package-lock.json`, termasuk alat build dan tes | Ada celah tingkat *moderate* ke atas |
| Audit Node | `npm audit signatures` (npm 11, lihat catatan di workflow) | Tanda tangan registry dan provenance setiap paket | Ada paket yang tanda tangannya tidak sah |

Alat build dan tes (Vite, Vitest) ikut diaudit karena keduanya menjalankan kode di laptop tim
dan di runner CI, walaupun tidak ikut ke hasil build yang dipakai pengguna.

## Menjalankan di laptop

Backend, dari folder `backend/` dengan venv aktif:

```powershell
python -m pip install pip-audit
pip-audit -r constraints.txt --no-deps --disable-pip --desc on
```

Frontend, dari folder `frontend/`:

```powershell
npm audit
```

## Menindaklanjuti temuan

1. Baca advisory yang ditautkan: paket mana, versi berapa yang aman, dan apakah fitur yang
   rentan memang dipakai.
2. **Python:** naikkan versi di `backend/constraints.txt` ke versi perbaikan (kolom *Fix
   Versions*). Bila batas di `pyproject.toml` menghalangi, longgarkan batasnya. Lalu install
   ulang dengan `python -m pip install -c constraints.txt -e ".[dev]"`, jalankan `pytest`, dan
   pastikan `pip check` bersih.
3. **Node:** jalankan `npm audit fix`. Bila perbaikannya butuh versi mayor baru (`npm audit`
   menyebut *breaking change*), naikkan versinya di `package.json` dengan `npm install -D
   <paket>@<versi>`, lalu jalankan `npm run build` dan `npm test`. Bila celahnya ada di
   dependency tidak langsung dan paket induknya belum merilis perbaikan, pakai `overrides` di
   `package.json`.
4. Buat pull request perbaikan dengan judul `fix(deps): ...` dan sebut ID advisory-nya.

## Bila belum ada perbaikan

Bila belum ada versi yang aman dan fitur yang rentan tidak dipakai, celah boleh dikecualikan
sementara. Tambahkan `--ignore-vuln <ID>` di workflow (Python) atau `overrides` ke versi yang
tidak terdampak (Node), dan catat di tabel di bawah. Tinjau ulang setiap minggu saat audit
terjadwal.

| ID advisory | Paket | Alasan aman sementara | Dicatat oleh, tanggal | Jira |
| --- | --- | --- | --- | --- |
| (belum ada) | | | | |

## Riwayat temuan

| Tanggal | Temuan | Tindakan |
| --- | --- | --- |
| 2026-11-15 | `certifi` 2026.7.22 (PYSEC-2026-4320), `opentelemetry-api` 1.45.0 (CVE-2026-114603, CVE-2026-126360), `vite` 7.3.6 (5 advisory termasuk GHSA-9jrq-w75r-8gcw), `vitest` 3.2.7 dengan `tinypool` dan `@vitest/mocker` (2 kritis, 1 moderate) | `certifi` 2026.10.23, `opentelemetry-api` 1.45.2, `vite` 7.3.8, `vitest` 5.1.0. Build, 47 tes frontend, dan tes backend tetap lulus. |
| 2026-11-16 | `npm audit signatures` gagal `EMISSINGSIGNATUREKEY` untuk `magic-string` 1.4.5: attestation provenance-nya tidak bisa dicocokkan npm 10 bawaan Node 22.12 dengan kunci registry | Langkah verifikasi memakai npm 11.21.2 lewat `npx`; paketnya tidak diubah |
