# Aturan Pull Request dan Review

Dokumen ini melengkapi [`BRANCH_WORKFLOW.md`](BRANCH_WORKFLOW.md). Semua perubahan ke `main` masuk lewat pull request (PR); tidak ada push langsung ke `main`.

## 1. Penamaan

| Hal | Format | Contoh |
| --- | --- | --- |
| Branch | `<tipe>/DIG-<no>-<deskripsi-singkat>` | `feat/DIG-12-import-csv`, `fix/DIG-40-timeline-kosong` |
| Commit | `<tipe>(<modul>): <ringkasan>` + `DIG-<no>` di badan commit | `feat(data): validasi kolom wajib CSV` |
| Judul PR | `<tipe>(<modul>): <ringkasan> [DIG-<no>]` | `feat(data): import CSV master data [DIG-12]` |

Tipe: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`. Modul: `data`, `digital-twin`, `simulasi`, `evaluasi`, `shared`, `devops`.

Kunci `DIG-<no>` di nama branch, commit, atau judul PR membuat branch, commit, dan PR otomatis tampil di panel Development issue Jira (jika integrasi GitHub for Jira aktif). Satu PR sebaiknya menyelesaikan satu issue.

Branch modul jangka panjang (`data`, `digital-twin`, `simulasi`, `evaluasi`) tetap dipakai sebagai tempat integrasi modul; branch fitur kecil dibuat dari branch modul tersebut atau dari `main` sesuai cakupannya.

## 2. Sebelum membuka PR (penulis)

1. Rebase/merge `main` terbaru dan pastikan tidak ada konflik.
2. Jalankan pemeriksaan yang sama dengan CI: build frontend, `ruff check`, `ruff format --check`, `pytest`.
3. Isi template PR lengkap: issue Jira, ringkasan, cara menguji, dan checklist.
4. Jaga ukuran PR tetap kecil — idealnya < 400 baris perubahan di luar file lock/migrasi. PR besar dipecah per modul atau per lapisan (model → service → router → UI).
5. Buka sebagai **Draft** jika masih dikerjakan; ubah ke **Ready for review** saat siap.
6. Pindahkan issue Jira ke status review/In Review.

## 3. Syarat merge

- Minimal **1 approval** dari anggota tim selain penulis.
- Perubahan di fondasi bersama (`frontend/src/app/`, `frontend/src/shared/`, `frontend/src/styles/`, `backend/app/api/`, `backend/app/core/`, `backend/app/db/`, `backend/migrations/`, `.github/`) membutuhkan **2 approval** karena berdampak ke semua modul.
- Semua check CI (`Frontend (typecheck + build)` dan `Backend (ruff + pytest)`) hijau.
- Semua komentar review sudah dijawab/di-resolve.
- Tidak ada konflik dengan `main`.
- Metode merge: **Squash and merge**, dengan judul squash mengikuti format judul PR.
- Hapus branch setelah merge.

## 4. Panduan reviewer

- Review dalam **1 hari kerja** sejak PR siap; jika tidak sempat, beri tahu di PR.
- Fokus berurutan: kebenaran logika → kontrak API/data antarmodul → migrasi database → tes → keterbacaan.
- Untuk migrasi: cek `upgrade` dan `downgrade` simetris, dan `alembic heads` tetap satu.
- Untuk UI: cek konsistensi dengan design system dan tampilan saat data kosong/error.
- Bedakan komentar wajib dan saran. Awali saran dengan `nit:` atau `saran:`; komentar tanpa awalan dianggap perlu ditangani sebelum merge.
- Gunakan **Request changes** hanya untuk masalah yang menghalangi merge.

## 5. Kode buatan AI (Copilot, Claude, dsb.)

Perlakukan sama seperti kode manusia: wajib lewat PR, wajib lolos CI, dan wajib di-review. Penulis yang membuka PR bertanggung jawab atas isinya dan harus memahami setiap perubahan. Jangan menerima file hasil generate yang tidak dibutuhkan (laporan PDF, file build, dsb.).

## 6. Pengaturan GitHub yang perlu diaktifkan admin repo

Pengaturan ini hanya bisa diubah pemilik/admin repository (Settings → Branches → Branch protection rules / Rulesets untuk `main`):

- [ ] Require a pull request before merging — required approvals: 1
- [ ] Dismiss stale pull request approvals when new commits are pushed
- [ ] Require status checks to pass: `Frontend (typecheck + build)`, `Backend (ruff + pytest)` (muncul setelah workflow CI pertama kali berjalan)
- [ ] Require branches to be up to date before merging
- [ ] Require conversation resolution before merging
- [ ] Block force pushes dan deletion pada `main`
- [ ] Settings → General → Pull Requests: izinkan hanya **Squash merging** dan aktifkan **Automatically delete head branches**
