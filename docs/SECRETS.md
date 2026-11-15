# Pengelolaan rahasia (DIG-125)

Dokumen ini mengatur di mana kredensial aplikasi J&C disimpan, siapa yang memegangnya, dan cara menggantinya. Aturan utamanya: **tidak ada rahasia di repository**. Tes `backend/tests/test_secrets.py` di CI menolak berkas `.env` yang ter-commit dan pola token yang dikenali (Trello, GitLab, GitHub, private key).

## Daftar rahasia

| Variabel | Dipakai untuk | Wajib | Hak minimum |
| --- | --- | --- | --- |
| `JWT_SECRET_KEY` | Menandatangani token login (DIG-17) | Ya, di luar development nilainya wajib diganti | Acak, minimal 32 karakter |
| `DATABASE_URL` | Koneksi aplikasi ke PostgreSQL; berisi password | Ya | Di staging pakai role `jc_app` (PR #14, docs/DATABASE_ROLES.md), bukan pemilik basis data |
| `TRELLO_API_KEY`, `TRELLO_API_TOKEN` | Konektor Trello API (DIG-119), hanya bila `TRELLO_API_ENABLED=true` | Tidak | Token dengan scope **read** saja |
| `TEAMGIT_TOKEN` | Konektor TeamGit (DIG-122) | Tidak | Hanya baca repository (misalnya `read_repository`/`read_api` bila TeamGit berbasis GitLab) |
| `NOTIFY_WEBHOOK_URL` | Notifikasi job impor gagal (DIG-129, docs/IMPORT_PIPELINE.md) | Tidak | Incoming webhook satu kanal tim saja |

`TRELLO_API_ENABLED`, `TEAMGIT_BASE_URL`, dan `APP_ENV` bukan rahasia.

## Tempat penyimpanan per lingkungan

| Lingkungan | Cara | Catatan |
| --- | --- | --- |
| Lokal (development) | `backend/.env`, disalin dari `.env.example` | `.env` sudah di `.gitignore`. Isi kredensial Trello/TeamGit milik sendiri, jangan dibagikan lewat chat. |
| CI (GitHub Actions) | Tidak butuh rahasia | Tes memakai basis data sementara dan `MockTransport`; tidak ada panggilan ke Trello atau TeamGit sungguhan. |
| Staging (DIG-49) | **Berkas rahasia** di folder yang ditunjuk `SECRETS_DIR` (misalnya Docker/Compose secrets di `/run/secrets`), atau environment dari layanan hosting | Satu berkas per rahasia, nama = nama variabel huruf kecil: `jwt_secret_key`, `database_url`, `trello_api_key`, `trello_api_token`, `teamgit_token`, `notify_webhook_url`. Hak berkas `600`, pemilik user yang menjalankan API. |
| Pipeline deploy (DIG-205) | GitHub Actions secrets di repository | Hanya untuk kredensial deploy (SSH/registry), bukan untuk menyalin rahasia aplikasi ke log. |

Urutan prioritas saat aplikasi membaca pengaturan: environment, lalu `backend/.env`, lalu berkas di `SECRETS_DIR`. Jadi berkas rahasia di server tidak tertimpa kecuali ada variabel environment dengan nama yang sama.

Contoh Compose untuk staging:

```yaml
services:
  api:
    environment:
      APP_ENV: staging
      SECRETS_DIR: /run/secrets
    secrets: [jwt_secret_key, database_url, trello_api_key, trello_api_token]
secrets:
  jwt_secret_key:
    file: ./secrets/jwt_secret_key   # folder ./secrets di luar repository, hak 600
```

## Aturan pemakaian di kode

- Simpan sebagai `SecretStr`, ambil nilainya dengan `get_secret_value()` hanya tepat saat dipakai.
- Jangan menaruh rahasia di URL atau query string; Trello memakai header `Authorization` (lihat docs/TRELLO_API.md).
- Jangan mencetak objek pengaturan atau header request ke log. `repr` pengaturan sudah menyamarkan rahasia (`**********`), dan pesan error konektor tidak memuat token.
- Pengaturan baru yang berisi rahasia ditambahkan ke tabel di atas dan ke `backend/.env.example` dengan nilai **kosong**.

## Rotasi dan kebocoran

| Kejadian | Langkah |
| --- | --- |
| Rotasi berkala (per semester) atau anggota pemegang akses keluar tim | Buat kredensial baru, ganti berkas di server, restart API, lalu cabut yang lama. |
| `JWT_SECRET_KEY` diganti | Semua token login lama otomatis tidak berlaku; pengguna cukup login ulang. |
| Token Trello bocor | Cabut di pengaturan akun Trello (*Applications*), buat token baru dengan scope read, ganti `trello_api_token`. |
| Token TeamGit bocor | Cabut di pengaturan akun TeamGit, buat token baru dengan hak baca saja, ganti `teamgit_token`. |
| URL webhook bocor | Hapus webhook di pengaturan kanal, buat yang baru, ganti `notify_webhook_url`. |
| Rahasia ter-commit | Anggap bocor: cabut dan ganti dulu, baru hapus dari repository. Menghapus commit saja tidak cukup karena riwayat dan salinan lain tetap ada. |

Pemegang rahasia staging dicatat di luar repository oleh penanggung jawab DevOps.
