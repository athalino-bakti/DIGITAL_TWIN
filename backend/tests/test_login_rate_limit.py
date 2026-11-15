"""Batas percobaan login gagal, tanpa basis data dan dengan jam palsu."""

from app.modules.auth import rate_limit
from app.modules.auth.rate_limit import LoginRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(max_per_user=5, max_per_ip=20, window=900.0):
    clock = FakeClock()
    return LoginRateLimiter(max_per_user, max_per_ip, window, clock=clock), clock


def test_user_is_blocked_after_max_failures_until_window_passes():
    limiter, clock = make()
    for _ in range(4):
        limiter.record_failure("bagas", "10.0.0.1")
        clock.now += 10
    assert limiter.retry_after("bagas", "10.0.0.1") is None

    limiter.record_failure("bagas", "10.0.0.1")  # gagal ke-5 pada t=1040
    # Terbuka lagi saat gagal pertama (t=1000) keluar dari jendela 900 detik.
    assert limiter.retry_after("bagas", "10.0.0.1") == 860

    clock.now = 1000 + 900  # gagal pertama sudah lewat jendela, tinggal 4
    assert limiter.retry_after("bagas", "10.0.0.1") is None


def test_retry_after_counts_from_the_oldest_failure_that_still_blocks():
    limiter, clock = make(max_per_user=2)
    limiter.record_failure("bagas", "a")
    clock.now += 100
    limiter.record_failure("bagas", "a")
    clock.now += 50
    assert limiter.retry_after("bagas", "b") == 900 - 150


def test_users_and_ips_are_counted_separately():
    limiter, _ = make(max_per_user=2, max_per_ip=3)
    limiter.record_failure("bagas", "a")
    limiter.record_failure("bagas", "a")

    assert limiter.retry_after("bagas", "b") is not None
    assert limiter.retry_after("davi", "b") is None
    assert limiter.retry_after("davi", "a") is None  # IP a baru 2 dari 3

    limiter.record_failure("citra", "a")
    assert limiter.retry_after("davi", "a") is not None


def test_success_clears_only_the_user_counter():
    limiter, _ = make(max_per_user=2, max_per_ip=3)
    limiter.record_failure("bagas", "a")
    limiter.record_failure("bagas", "a")
    limiter.record_success("bagas")

    assert limiter.retry_after("bagas", "b") is None
    limiter.record_failure("davi", "a")
    assert limiter.retry_after("bagas", "a") is not None, "hitungan IP tetap berjalan"


def test_tracked_keys_are_bounded(monkeypatch):
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_KEYS", 10)
    limiter, clock = make()
    for i in range(50):
        limiter.record_failure(f"user{i}", f"ip{i}")
        clock.now += 1
    assert len(limiter._failures) <= 10
    assert limiter.retry_after("user49", "ip49") is None  # 1 kali gagal, belum diblokir


def test_settings_feed_the_shared_limiter(monkeypatch):
    monkeypatch.setattr(rate_limit, "_limiter", None)
    limiter = rate_limit.get_login_limiter()
    assert (limiter.max_per_user, limiter.max_per_ip, limiter.window) == (5, 20, 15 * 60)
    assert rate_limit.get_login_limiter() is limiter
