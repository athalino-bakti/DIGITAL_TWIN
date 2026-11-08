"""Mengambil satu papan Trello lewat REST API dalam bentuk yang sama dengan ekspor JSON.

Ekspor JSON dari menu Trello (Menu > Print, export, and share > Export as JSON) berisi
objek papan dengan kunci lists, cards, members, labels, dan actions. Konektor ini
menyusun objek yang sama dari beberapa endpoint API, sehingga parser ekspor (DIG-118)
bisa dipakai untuk kedua sumber tanpa perubahan.

Bedanya dengan ekspor manual: ekspor dari menu Trello dilaporkan hanya memuat 1000 action
terbaru (lihat docs/TRELLO_API.md), sedangkan konektor ini menelusuri seluruh riwayat action
dengan paginasi `before`.

Batas Trello: 100 request per 10 detik per token dan maksimal 1000 hasil per request.
Respons 429 dicoba ulang dengan jeda bertahap.
"""

import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.integrations.trello.config import TrelloSettings, get_trello_settings

# ID papan: 24 karakter heksadesimal, atau shortLink 8 karakter dari URL trello.com/b/<shortLink>.
BOARD_ID_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{24}|[A-Za-z0-9]{8})$")
PAGE_LIMIT = 1000

# Action yang dibutuhkan untuk menurunkan status, phase, pelaku, dan waktu kartu.
ACTION_FILTER = ",".join(
    [
        "createCard",
        "copyCard",
        "convertToCardFromCheckItem",
        "moveCardToBoard",
        "moveCardFromBoard",
        "updateCard",
        "deleteCard",
        "addMemberToCard",
        "removeMemberFromCard",
        "createList",
        "updateList",
    ]
)
MEMBER_FIELDS = "fullName,username,initials"


class TrelloError(Exception):
    """Kegagalan umum konektor Trello."""


class TrelloDisabledError(TrelloError):
    """Feature flag mati atau kredensial belum diisi."""


class TrelloAuthError(TrelloError):
    """Key/token ditolak (401) atau tidak punya akses ke papan (403)."""


class TrelloNotFoundError(TrelloError):
    """Papan tidak ditemukan atau ID tidak sah."""


class TrelloRateLimitError(TrelloError):
    """Masih kena batas request setelah semua percobaan ulang."""


class TrelloClient:
    def __init__(
        self,
        api_key: str,
        api_token: str,
        base_url: str = "https://api.trello.com/1",
        timeout: float = 30.0,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # Kredensial dikirim lewat header, bukan query string, supaya token tidak tercatat
        # di log URL server, proxy, atau pesan error.
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Authorization": f'OAuth oauth_consumer_key="{api_key}", oauth_token="{api_token}"',
            },
        )
        self._max_retries = max_retries
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"TrelloClient(base_url={str(self._http.base_url)!r})"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TrelloClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self._max_retries + 1):
            response = self._http.get(path, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self._max_retries:
                    if response.status_code == 429:
                        raise TrelloRateLimitError("Batas request Trello terlampaui, coba lagi")
                    raise TrelloError(f"Trello error {response.status_code}")
                self._sleep(_retry_delay(response, attempt))
                continue
            if response.status_code in (401, 403):
                raise TrelloAuthError(
                    "Trello menolak key/token atau token tidak punya akses ke papan ini"
                )
            if response.status_code in (400, 404):
                raise TrelloNotFoundError("Papan Trello tidak ditemukan")
            response.raise_for_status()
            return response.json()
        raise TrelloError("Gagal menghubungi Trello")  # tidak tercapai

    def fetch_actions(self, board_id: str) -> list[dict[str, Any]]:
        """Seluruh action papan, terbaru lebih dulu (urutan sama dengan ekspor Trello)."""
        actions: list[dict[str, Any]] = []
        before: str | None = None
        while True:
            params: dict[str, Any] = {
                "filter": ACTION_FILTER,
                "limit": PAGE_LIMIT,
                "memberCreator_fields": MEMBER_FIELDS,
            }
            if before:
                params["before"] = before
            page = self._get(f"/boards/{board_id}/actions", params)
            actions.extend(page)
            if len(page) < PAGE_LIMIT:
                return actions
            # ID action mengandung waktu kejadian; ID terakhir jadi batas halaman berikutnya.
            before = page[-1]["id"]

    def fetch_board_export(self, board_id: str) -> dict[str, Any]:
        """Objek papan berbentuk ekspor JSON Trello."""
        if not BOARD_ID_PATTERN.match(board_id):
            raise TrelloNotFoundError("ID papan Trello tidak sah")

        board = self._get(
            f"/boards/{board_id}",
            {"fields": "name,desc,url,shortLink,closed,dateLastActivity,idOrganization"},
        )
        board_key = board["id"]
        board["lists"] = self._get(
            f"/boards/{board_key}/lists", {"filter": "all", "fields": "name,closed,pos,idBoard"}
        )
        board["cards"] = self._get(
            f"/boards/{board_key}/cards",
            {
                "filter": "all",
                "fields": (
                    "name,idList,idBoard,closed,pos,start,due,dueComplete,dateLastActivity,"
                    "idMembers,idLabels,shortLink,url"
                ),
            },
        )
        board["members"] = self._get(f"/boards/{board_key}/members", {"fields": MEMBER_FIELDS})
        board["labels"] = self._get(f"/boards/{board_key}/labels", {"fields": "name,color"})
        board["actions"] = self.fetch_actions(board_key)
        return board


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    # Batas token Trello dihitung per jendela 10 detik.
    return min(2.0 * 2**attempt, 30.0)


def client_from_settings(
    settings: TrelloSettings | None = None, transport: httpx.BaseTransport | None = None
) -> TrelloClient:
    """Buat client dari konfigurasi; gagal bila feature flag mati atau kredensial kosong."""
    settings = settings or get_trello_settings()
    if not settings.api_enabled:
        raise TrelloDisabledError("Konektor Trello API nonaktif (TRELLO_API_ENABLED=false)")
    if settings.api_key is None or settings.api_token is None:
        raise TrelloDisabledError("TRELLO_API_KEY dan TRELLO_API_TOKEN wajib diisi")
    return TrelloClient(
        api_key=settings.api_key.get_secret_value(),
        api_token=settings.api_token.get_secret_value(),
        base_url=settings.api_base_url,
        transport=transport,
    )
