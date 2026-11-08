# Konektor Trello API (DIG-119)

Story DIG-26 mengimpor riwayat kartu Trello ke staging. Sumber utamanya adalah **berkas ekspor JSON papan** (parser DIG-118). Konektor ini adalah jalur **opsional**: data papan diambil langsung dari Trello REST API dalam **bentuk yang sama dengan ekspor JSON**, sehingga parser yang sama bisa dipakai untuk kedua sumber.

Konektor **mati secara default** dan hanya aktif bila `TRELLO_API_ENABLED=true`.

## Kenapa ada jalur API

| | Ekspor JSON manual | Konektor API |
| --- | --- | --- |
| Cara | Menu papan → *Print, export, and share* → *Export as JSON* | `python -m app.integrations.trello.fetch_board` |
| Kredensial | Tidak perlu | API key + token |
| Jumlah action | Dilaporkan terbatas 1000 action terbaru* | Seluruh riwayat, dengan paginasi |
| Otomatisasi | Manual tiap kali | Bisa dijadwalkan (DIG-127) |

\* Batas 1000 action pada ekspor manual berasal dari laporan pengguna di forum Atlassian, bukan dokumentasi resmi. Perlu dicek pada papan PuTI: bila jumlah action di berkas ekspor tepat 1000, kemungkinan riwayat lama terpotong dan jalur API dibutuhkan.

## Endpoint yang dipakai

Semua `GET` ke `https://api.trello.com/1`:

| Endpoint | Kunci di hasil | Keterangan |
| --- | --- | --- |
| `/boards/{id}` | atribut papan | `{id}` boleh shortLink dari URL; ID 24 karakter dipakai untuk request berikutnya |
| `/boards/{id}/lists?filter=all` | `lists` | Termasuk list yang diarsipkan |
| `/boards/{id}/cards?filter=all` | `cards` | Termasuk kartu yang diarsipkan |
| `/boards/{id}/members` | `members` | |
| `/boards/{id}/labels` | `labels` | |
| `/boards/{id}/actions?limit=1000&before=…` | `actions` | Terbaru lebih dulu, diulang sampai halaman < 1000 |

Filter action: `createCard`, `copyCard`, `convertToCardFromCheckItem`, `moveCardToBoard`, `moveCardFromBoard`, `updateCard`, `deleteCard`, `addMemberToCard`, `removeMemberFromCard`, `createList`, `updateList`. Perpindahan status ada di action `updateCard` dengan `data.listBefore` dan `data.listAfter`; pelakunya di `memberCreator`, waktunya di `date`.

## Batas dan penanganan error

- **Rate limit:** 100 request per 10 detik per token, 300 per 10 detik per API key. Satu papan butuh 5 request ditambah 1 request per 1000 action, jadi jauh di bawah batas.
- **429 dan 5xx:** dicoba ulang maksimal 4 kali dengan jeda 2, 4, 8, 16 detik (atau sesuai header `Retry-After` bila ada).
- **401/403:** key/token salah atau tidak punya akses ke papan. Tidak dicoba ulang.
- **400/404 atau ID tidak sah:** papan tidak ditemukan. ID dicek dengan pola sebelum request dikirim.

## Keamanan kredensial

- Key dan token dikirim lewat header `Authorization: OAuth oauth_consumer_key="…", oauth_token="…"`, **tidak** lewat query string, sehingga tidak tercatat di log URL.
- Kredensial disimpan sebagai `SecretStr` dan tidak muncul di `repr` atau pesan error.
- Buat token dengan scope **read** saja. Token tidak pernah di-commit; isi lewat `.env` lokal. Penyimpanan rahasia di server staging dibahas di DIG-125.

## Cara mencoba

1. Ambil API key dan buat token (scope read) di <https://trello.com/app-key>.
2. Isi di `backend/.env`:
   ```
   TRELLO_API_ENABLED=true
   TRELLO_API_KEY=<key>
   TRELLO_API_TOKEN=<token>
   ```
3. Dari folder `backend`:
   ```powershell
   python -m app.integrations.trello.fetch_board --board <shortLink> --out board.json
   ```
   `<shortLink>` adalah 8 karakter setelah `trello.com/b/` pada URL papan. Perintah menampilkan jumlah list, kartu, anggota, dan action per jenis.
4. Berkas `board.json` dapat diproses parser DIG-118 seperti berkas ekspor manual.

## Pemakaian di kode

```python
from app.integrations.trello.client import TrelloError, client_from_settings

try:
    with client_from_settings() as client:
        board = client.fetch_board_export("AbCd1234")
except TrelloError as exc:
    ...  # nonaktif, kredensial ditolak, papan tidak ada, atau rate limit
```

`client_from_settings()` melempar `TrelloDisabledError` bila feature flag mati atau kredensial kosong, sehingga endpoint impor bisa menampilkan opsi API hanya saat konektor aktif.
