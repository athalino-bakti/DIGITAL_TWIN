<!--
Judul PR: <tipe>(<modul>): <ringkasan> [DIG-<no Story>]
Contoh : feat(data): kelola proyek [DIG-20]
Satu PR = satu Story. Subtask cukup jadi commit di branch yang sama.
Tipe   : feat | fix | refactor | docs | test | chore | ci
Aturan lengkap: docs/PR_REVIEW.md
-->

## Issue Jira

Story: DIG-

Subtask yang diselesaikan:

- DIG-

## Ringkasan perubahan

<!-- Apa yang berubah dan kenapa. 2–5 poin singkat. -->

-

## Modul terdampak

- [ ] Data
- [ ] Digital Twin
- [ ] Simulasi
- [ ] Evaluasi
- [ ] Fondasi bersama (layout, `shared/`, konfigurasi, router utama, design system)
- [ ] DevOps / dokumentasi

## Jenis perubahan

- [ ] Fitur baru
- [ ] Perbaikan bug
- [ ] Refactor (tanpa perubahan perilaku)
- [ ] Dokumentasi / CI / tooling

## Cara menguji

<!-- Langkah yang bisa diikuti reviewer, termasuk endpoint, halaman, atau data contoh. -->

1.

## Database & migrasi

- [ ] Tidak ada perubahan skema
- [ ] Ada migrasi Alembic baru; sudah diuji `alembic upgrade head` **dan** `alembic downgrade -1`
- [ ] `alembic heads` hanya menghasilkan satu head

## Checklist penulis

- [ ] Branch dibuat dari `main` terbaru dan sesuai modulnya (lihat `docs/BRANCH_WORKFLOW.md`)
- [ ] CI hijau: build frontend, `ruff check`, `ruff format --check`, `pytest`
- [ ] Tes ditambahkan/diperbarui untuk perilaku yang berubah
- [ ] Tidak ada rahasia, file `.env`, atau file hasil build/binary yang tidak perlu
- [ ] Dependency baru dicatat di `pyproject.toml` + `constraints.txt` atau `package-lock.json`
- [ ] Perubahan UI mengikuti design system (`frontend/src/styles/tokens.css`, `components.css`)
- [ ] Dokumentasi/README diperbarui jika cara menjalankan atau kontrak API berubah

## Screenshot (jika ada perubahan UI)

<!-- Sebelum / sesudah -->
