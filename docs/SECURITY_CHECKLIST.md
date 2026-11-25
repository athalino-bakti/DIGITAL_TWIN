# Pemeriksaan keamanan dasar (DIG-208)

Pemeriksaan OWASP Top 10 (2021) terhadap kode di `main` per 16 November 2026, ditambah daftar
header keamanan. Dipakai sebagai bahan story DIG-50 (ISO/IEC 25010 karakteristik *security*,
kontrol ISO/IEC 27001 yang relevan). Perbarui tabel ini setiap ada perubahan yang menyentuh
autentikasi, izin, impor data, atau deployment.

Status: **Ada** = kontrol terpasang dan dites, **Sebagian** = ada tetapi dengan batasan yang
dicatat, **Belum** = perlu dikerjakan (lihat Jira).

## OWASP Top 10

| Risiko | Status | Kontrol yang ada | Celah atau batasan |
| --- | --- | --- | --- |
| A01 Broken Access Control | Ada | Semua endpoint `/api/v1/data/*` wajib login dan izin; `tests/test_data_permissions.py` gagal bila ada endpoint data tanpa `require_permission` (DIG-226). Endpoint Digital Twin yang sedang di-review (#32, #33, #38) memakai `baseline:read`. Endpoint "Task saya" mengecek pelaksana aktif task (403 untuk task orang lain). Izin dibaca ulang setiap request. | Matriks uji akses untuk semua endpoint di luar `/data` masih DIG-207. Pembatasan data pribadi (DIG-19) dijelaskan di bagian "Data pribadi". |
| A02 Cryptographic Failures | Sebagian | Password di-hash scrypt (N=2^15, r=8, p=3) dan di-hash ulang bila parameter naik. JWT HS256 dengan rahasia minimal 32 karakter; nilai development ditolak di luar `APP_ENV=development`. | HTTPS belum ada sampai server staging (DIG-206). HSTS sudah disiapkan (`STRICT_TRANSPORT_SECURITY`) tetapi baru boleh diisi setelah HTTPS. |
| A03 Injection | Ada | Query lewat SQLAlchemy dengan parameter; tidak ada SQL dari string pengguna. Input divalidasi Pydantic (pola ID, panjang maksimal). Frontend React meng-escape teks; CSP `script-src 'self'` memblokir skrip sisipan. `src/security.test.ts` menolak `dangerouslySetInnerHTML`, `innerHTML`, `eval`, dan `<style>` di kode frontend. | `app/qa/schema_check.py` menjalankan ekspresi CHECK dari DATA_CONTRACT di tabel sementara; titik koma di luar teks berkutip ditolak dan transaksinya selalu di-rollback. Alat ini hanya untuk tim, bukan endpoint. |
| A04 Insecure Design | Sebagian | Aturan bisnis diperiksa di service dan di constraint basis data (CHECK, FK, index unik parsial, exclusion constraint); pelanggaran bersamaan menjadi 409, bukan 500. Deteksi overrun otomatis terkunci di `OVERRUN_DETECTION_ENABLED=false`. | Belum ada audit log siapa mengubah apa (DIG-222). |
| A05 Security Misconfiguration | Ada | Header keamanan di nginx dan API (bagian berikut). Container berjalan tanpa root; API dan basis data tidak membuka port ke host. Versi nginx tidak ditampilkan. CORS hanya origin yang terdaftar, tanpa credentials. | Halaman `/docs`, `/redoc`, dan `/openapi.json` FastAPI aktif bila API dibuka langsung; di staging tidak terjangkau karena nginx hanya meneruskan `/api/`. Aturan: konfigurasi nginx atau proxy produksi tidak boleh meneruskan path itu, dan port API tidak dibuka ke luar. |
| A06 Vulnerable and Outdated Components | Ada | Workflow *Audit dependency*: `pip-audit` dan `npm audit` di setiap PR dan setiap Senin (DIG-209, `docs/DEPENDENCY_AUDIT.md`). Versi Python dipin di `constraints.txt`, Node di `package-lock.json`. | Image dasar Docker (`python:3.11-slim`, `nginx-unprivileged`) belum dipindai; bisa ditambah saat pipeline deploy (DIG-205). |
| A07 Identification and Authentication Failures | Sebagian | Batas login gagal 5 per akun dan 20 per IP dalam 15 menit (429); hash dummy mencegah tebakan nama akun lewat waktu respons; pesan gagal sama untuk akun salah dan password salah. Token berlaku 60 menit. | Token disimpan di `localStorage` dan tidak bisa dicabut sebelum kedaluwarsa (logout hanya menghapus di browser). CSP mengurangi risiko pencurian lewat XSS. Batas login dihitung per proses API (satu worker di `compose.prod.yaml`). |
| A08 Software and Data Integrity Failures | Ada | `npm ci` dari lockfile dan `npm audit signatures` di CI; dependency Python dipin. Impor data ke staging dalam satu transaksi dan aman diulang. | Belum ada tanda tangan image Docker (bagian DIG-205). |
| A09 Security Logging and Monitoring Failures | Belum | Job impor tercatat di `import_job` dan log terstruktur (DIG-128, PR #34). | Login gagal, penolakan izin (403), dan perubahan data belum dicatat ke log. Usul: log WARNING terstruktur untuk 401/403/429 tanpa password atau token, bersama audit log DIG-222. |
| A10 Server-Side Request Forgery | Ada | Konektor Trello memakai URL dasar tetap (`https://api.trello.com/1`); ID papan dari konfigurasi server, bukan dari pengguna. Tidak ada endpoint yang mengambil URL dari pengguna. | URL TeamGit dan webhook notifikasi juga dari konfigurasi server, bukan pengguna. |

## Header keamanan

Dipasang nginx untuk semua respons (`frontend/nginx/default.conf.template`):

| Header | Nilai | Tujuan |
| --- | --- | --- |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'` | Hanya skrip dan gaya dari origin sendiri (plus Google Fonts); tidak bisa dibingkai situs lain |
| `X-Content-Type-Options` | `nosniff` | Browser tidak menebak jenis berkas |
| `X-Frame-Options` | `DENY` | Perlindungan clickjacking untuk browser lama |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Path dan query tidak bocor ke situs lain |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=(), usb=()` | Fitur browser yang tidak dipakai dimatikan |
| `Cross-Origin-Opener-Policy` | `same-origin` | Jendela situs lain tidak bisa mengakses tab aplikasi |
| `Strict-Transport-Security` | kosong (tidak dikirim) | Diisi `max-age=31536000` lewat `STRICT_TRANSPORT_SECURITY` setelah HTTPS aktif (DIG-206) |

API memasang header serupa sendiri (`app/core/security_headers.py`) supaya tetap aman bila
dibuka tanpa nginx, ditambah `Cache-Control: no-store` agar data kerja tidak tersimpan di cache.
Di balik nginx, header ganda dari API disembunyikan sehingga tiap header hanya terkirim sekali.

Cara memeriksa:

- Workflow *Docker* memeriksa semua header di atas untuk halaman dan respons API.
- `tests/test_security_headers.py` memeriksa header API, termasuk respons error dan preflight CORS.
- `frontend/src/security.test.ts` gagal bila kode frontend memakai pola yang akan diblokir CSP.
- Uji manual 16 November 2026: build produksi dibuka di Chrome headless di balik nginx dengan
  CSP di atas; login, semua tab Data, tab Digital Twin, dan dialog Tambah proyek berjalan tanpa
  pelanggaran CSP maupun error di console.

## Data pribadi (DIG-19)

| Kriteria | Kontrol | Tes |
| --- | --- | --- |
| Heatmap seluruh anggota dan D-09 availability hanya untuk Kaur/Asman dan System Analyst | `GET /data/availability`, `/data/workload-items`, dan `/data/change-events` memakai `workload:read_all`. Heatmap tanpa `workload:read_all` hanya mengembalikan baris anggota yang tertaut ke akun; filter `role_id` dan `resource_id` diabaikan. | `tests/test_data_privacy.py` (matriks lima peran) |
| Anggota tim hanya melihat task dan beban miliknya | `GET /data/tasks` dan `/data/tasks/{id}` tanpa `workload:read_all` atau `master_data:write` hanya berisi task yang pernah atau sedang ditugaskan ke anggota yang tertaut ke akun; task orang lain dijawab 404. Akun yang belum ditautkan tidak melihat task apa pun. "Task saya" dan heatmap mengikuti aturan yang sama. | `tests/test_data_privacy.py` |
| Alamat surel commit tidak pernah ditampilkan | `app/core/privacy.py`: alias `teamgit` dikirim tersamar (`s***@puti.ac.id`) di semua respons `/data/resource-aliases`; identitas belum terpetakan diberi `alias_ref` (HMAC, tidak bisa dibalik) dan dipetakan lewat `alias_ref`, sehingga email asli tidak pernah sampai ke browser. Isi `before`, `after`, `note`, dan `entity_id` di `/data/audit-log` juga disamarkan. Nilai asli tetap tersimpan untuk pencocokan identitas. | `tests/test_data_privacy.py` |

Aturan untuk endpoint baru: data yang memuat email author commit (mis. staging commit di DIG-27) wajib melewati `mask_email` atau `mask_emails_deep` sebelum dikirim, dan pemetaan identitasnya memakai `alias_ref`.

## Tindak lanjut

| Butir | Jira |
| --- | --- |
| Matriks uji akses per peran untuk semua endpoint | DIG-207 |
| HTTPS dan HSTS di staging | DIG-206 |
| Audit log perubahan data, dan log login gagal serta penolakan izin | DIG-222 |
| Pemindaian image Docker dan tanda tangan image | DIG-205 |
