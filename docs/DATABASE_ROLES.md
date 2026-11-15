# Role dan Schema Basis Data

Ringkasan hak akses basis data bersama J&C dan tWinner sesuai `docs/DATA_CONTRACT.md` bagian 4 (DIG-12). Semua role dan schema dibuat lewat migrasi Alembic; hanya **login dan password** yang diatur admin di luar repository.

## Role

| Role | Dipakai oleh | Hak | Dibuat di |
| --- | --- | --- | --- |
| Pemilik basis data (mis. `puti` di `compose.yaml`) | Alembic saat menjalankan migrasi | Pemilik semua tabel; membuat dan mengubah struktur | Saat basis data dibuat |
| `jc_app` | Aplikasi J&C (backend FastAPI) | `SELECT`, `INSERT`, `UPDATE`, `DELETE` di schema `public`; hanya `SELECT` pada `alembic_version`; tanpa DDL, tanpa `TRUNCATE`, tanpa akses ke schema `twinner` | Migrasi `0014` (DIG-223) |
| `twinner_reader` | Aplikasi tWinner | Hanya `SELECT` pada final sources dan objek bagian 7.1 data contract | DIG-191 (belum) |

## Schema

| Schema | Pemilik isi | Keterangan |
| --- | --- | --- |
| `public` | J&C | Final sources D-01 s.d. D-11 dan tabel internal J&C |
| `twinner` | tWinner | Skenario dan hasil simulasi tWinner. J&C tidak menulis ke sini; `jc_app` tidak punya hak apa pun di schema ini |

## Perilaku migrasi `0014`

- `jc_app` dibuat **NOLOGIN tanpa password**, karena kredensial tidak boleh ada di repository.
- Hak `jc_app` berlaku untuk semua tabel yang sudah ada, dan lewat *default privileges* juga untuk tabel dan sequence yang dibuat migrasi berikutnya oleh role pemilik yang sama. Migrasi baru tidak perlu menulis `GRANT` lagi.
- Migrasi harus dijalankan role yang boleh membuat role (superuser atau `CREATEROLE`).
- Downgrade mencabut semua hak `jc_app` dan menghapus schema `twinner` **tanpa CASCADE**: bila tWinner sudah punya tabel di sana, downgrade gagal sehingga data tWinner tidak terhapus.
- Role `jc_app` tidak dihapus saat downgrade karena role berlaku untuk seluruh server PostgreSQL dan bisa masih dipakai basis data lain.

## Mengaktifkan login `jc_app` (staging dan production)

Dijalankan admin basis data sekali, di luar repository. Password disimpan di secret server, bukan di `.env.example` atau dokumen.

```sql
ALTER ROLE jc_app LOGIN PASSWORD '<password-kuat>';
```

Lalu backend memakai `jc_app` di `DATABASE_URL`, sedangkan migrasi tetap dijalankan dengan kredensial pemilik basis data. Pemisahan kredensial migrasi dan aplikasi diatur di pipeline deploy staging (DIG-205).

Untuk development lokal tidak ada yang perlu diubah: backend dan migrasi tetap memakai user `puti` dari `compose.yaml`.

## Hal yang masih perlu disepakati dengan tWinner

Data contract hanya mengatur role baca `twinner_reader`. Role yang dipakai tWinner untuk **menulis** ke schema `twinner` (membuat tabel skenario dan hasil simulasi) belum ditetapkan. Usulan: tetapkan bersama saat DIG-191, lalu catat di data contract bagian 4 lewat mekanisme perubahan kontrak bagian 9.
