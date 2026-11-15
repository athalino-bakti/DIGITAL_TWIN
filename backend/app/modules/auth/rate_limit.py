"""Batas percobaan login yang gagal, per username dan per alamat IP.

- Per username: setelah `LOGIN_MAX_FAILURES_PER_USER` kali gagal dalam jendela
  `LOGIN_LOCKOUT_MINUTES`, login untuk username itu ditolak 429 sampai jendelanya lewat.
  Ini menahan tebak password untuk satu akun.
- Per IP: setelah `LOGIN_MAX_FAILURES_PER_IP` kali gagal, semua login dari IP itu ditolak.
  Ini menahan satu sumber yang mencoba banyak username sekaligus.

Username yang tidak terdaftar dihitung dengan cara yang sama, jadi respons 429 tidak
membocorkan username mana yang ada. Login yang berhasil menghapus hitungan username itu.
Saat ditolak, password tidak di-hash sama sekali, jadi serangan tidak menghabiskan CPU dan
memori server.

Hitungan disimpan di memori satu proses. Bila API dijalankan dengan beberapa worker, setiap
worker punya hitungan sendiri, sehingga batas efektifnya dikali jumlah worker.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

MAX_TRACKED_KEYS = 10_000


class LoginRateLimiter:
    def __init__(
        self,
        max_per_user: int,
        max_per_ip: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_per_user = max_per_user
        self.max_per_ip = max_per_ip
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.get(key)
        if attempts is None:
            return deque()
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
        return attempts

    def retry_after(self, username: str, ip: str) -> int | None:
        """Detik sampai boleh mencoba lagi, atau None bila login boleh diproses."""
        now = self._clock()
        wait = 0.0
        with self._lock:
            for key, limit in (
                (f"user:{username}", self.max_per_user),
                (f"ip:{ip}", self.max_per_ip),
            ):
                attempts = self._recent(key, now)
                if len(attempts) >= limit:
                    wait = max(wait, attempts[-limit] + self.window - now)
        return max(1, math.ceil(wait)) if wait > 0 else None

    def record_failure(self, username: str, ip: str) -> None:
        now = self._clock()
        with self._lock:
            for key in (f"user:{username}", f"ip:{ip}"):
                if key not in self._failures and len(self._failures) >= MAX_TRACKED_KEYS:
                    self._drop_expired(now)
                self._failures.setdefault(key, deque()).append(now)

    def record_success(self, username: str) -> None:
        with self._lock:
            self._failures.pop(f"user:{username}", None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()

    def _drop_expired(self, now: float) -> None:
        for key in list(self._failures):
            self._recent(key, now)
        # Masih penuh setelah dibersihkan: buang yang paling lama tidak dipakai.
        while len(self._failures) >= MAX_TRACKED_KEYS:
            oldest = min(self._failures, key=lambda k: self._failures[k][-1])
            del self._failures[oldest]


_limiter: LoginRateLimiter | None = None


def get_login_limiter() -> LoginRateLimiter:
    global _limiter
    if _limiter is None:
        from app.core.config import get_settings

        settings = get_settings()
        _limiter = LoginRateLimiter(
            max_per_user=settings.login_max_failures_per_user,
            max_per_ip=settings.login_max_failures_per_ip,
            window_seconds=settings.login_lockout_minutes * 60,
        )
    return _limiter
