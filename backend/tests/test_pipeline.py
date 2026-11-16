"""DIG-127 s.d. DIG-129: bagian pipeline yang tidak butuh basis data."""

import json
import logging

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.integrations.trello.client import (
    TrelloAuthError,
    TrelloDisabledError,
    TrelloError,
    TrelloNotFoundError,
    TrelloRateLimitError,
)
from app.pipeline import run as cli
from app.pipeline.config import PipelineSettings
from app.pipeline.jobs import PermanentJobError, import_trello, is_transient
from app.pipeline.logging import QUIET_LOGGERS, JsonFormatter, TextFormatter, configure_logging
from app.pipeline.notify import MAX_MESSAGE, send_notification
from app.pipeline.runner import JobAlreadyRunning, redact

WEBHOOK = "https://hooks.example.test/services/T000/B000/rahasia-webhook"


def settings(**kwargs) -> PipelineSettings:
    return PipelineSettings(_env_file=None, **kwargs)


# --- konfigurasi ----------------------------------------------------------------------


def test_board_ids_are_split_and_trimmed():
    assert settings(trello_board_ids=" AbCd1234, ,5f1a2b3c4d5e6f7a8b9c0d1e ").board_ids == [
        "AbCd1234",
        "5f1a2b3c4d5e6f7a8b9c0d1e",
    ]
    assert settings().board_ids == []


def test_webhook_url_is_secret():
    s = settings(notify_webhook_url=WEBHOOK)
    assert "rahasia" not in repr(s)


# --- klasifikasi error --------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        TrelloRateLimitError("429"),
        TrelloError("500 terus"),
        httpx.ConnectError("putus"),
        httpx.ReadTimeout("lambat"),
        OperationalError("select 1", {}, Exception("server closed the connection")),
    ],
)
def test_temporary_errors_are_retried(exc):
    assert is_transient(exc)


@pytest.mark.parametrize(
    "exc",
    [
        TrelloAuthError("401"),
        TrelloNotFoundError("404"),
        TrelloDisabledError("mati"),
        PermanentJobError("konfigurasi"),
        ValueError("data rusak"),
    ],
)
def test_permanent_errors_are_not_retried(exc):
    assert not is_transient(exc)


def test_trello_job_without_boards_is_permanent_error():
    with pytest.raises(PermanentJobError, match="TRELLO_BOARD_IDS"):
        import_trello(db=None, settings=settings())


def test_trello_job_with_connector_disabled_is_permanent_error():
    from app.integrations.trello.config import TrelloSettings

    trello = TrelloSettings(_env_file=None, api_enabled=False)
    with pytest.raises(PermanentJobError, match="nonaktif"):
        import_trello(
            db=None, settings=settings(trello_board_ids="AbCd1234"), trello_settings=trello
        )


# --- penyamaran rahasia -----------------------------------------------------------------


def test_secrets_are_redacted_from_error_message():
    message = f"ConnectError: gagal ke {WEBHOOK}?token=abcd1234efgh"
    redacted = redact(message, [WEBHOOK, "abcd1234efgh", None, ""])
    assert "rahasia" not in redacted and "abcd1234efgh" not in redacted
    assert redacted.startswith("ConnectError: gagal ke ***")


def test_long_error_is_truncated():
    assert len(redact("x" * 10_000, [])) == 2000


# --- notifikasi (DIG-129) ---------------------------------------------------------------


def test_notification_posts_text_and_content():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    ok = send_notification(
        settings(notify_webhook_url=WEBHOOK), "Impor gagal", httpx.MockTransport(handler)
    )
    assert ok
    assert str(sent[0].url) == WEBHOOK
    assert json.loads(sent[0].content) == {"text": "Impor gagal", "content": "Impor gagal"}


def test_notification_is_truncated_for_discord_limit():
    sent = []
    transport = httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(204))
    send_notification(settings(notify_webhook_url=WEBHOOK), "x" * 5000, transport)
    assert len(json.loads(sent[0].content)["text"]) == MAX_MESSAGE


def test_notification_skipped_without_webhook():
    called = []
    transport = httpx.MockTransport(lambda r: called.append(r) or httpx.Response(200))
    assert send_notification(settings(), "pesan", transport) is False
    assert called == []


@pytest.mark.parametrize("failure", ["status", "network"])
def test_failed_notification_is_logged_without_url(failure, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ConnectError("tidak terjangkau")
        return httpx.Response(500)

    with caplog.at_level(logging.WARNING, logger="app.pipeline.notify"):
        ok = send_notification(
            settings(notify_webhook_url=WEBHOOK), "pesan", httpx.MockTransport(handler)
        )
    assert ok is False
    assert "notifikasi gagal" in caplog.text
    assert all("rahasia" not in str(vars(r)) for r in caplog.records)


# --- log terstruktur (DIG-128) ------------------------------------------------------------


def make_record(**extra) -> logging.LogRecord:
    record = logging.makeLogRecord(
        {"name": "app.pipeline", "levelname": "ERROR", "levelno": 40, "msg": "job impor gagal"}
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_log_is_one_object_with_extra_fields():
    line = JsonFormatter().format(make_record(job_id=7, source="trello", attempts=3))
    payload = json.loads(line)
    assert payload["level"] == "ERROR"
    assert payload["message"] == "job impor gagal"
    assert payload["job_id"] == 7 and payload["source"] == "trello" and payload["attempts"] == 3
    assert "\n" not in line


def test_text_log_shows_extra_fields():
    line = TextFormatter("%(levelname)s %(message)s").format(make_record(job_id=7))
    assert line == "ERROR job impor gagal {'job_id': 7}"


# --- CLI (DIG-127) ------------------------------------------------------------------------


class FakeJob:
    def __init__(self, status):
        self.status = status


@pytest.mark.parametrize(
    ("outcome", "code"),
    [(FakeJob("succeeded"), 0), (FakeJob("failed"), 1), (JobAlreadyRunning("trello", 4), 2)],
)
def test_cli_exit_code(monkeypatch, outcome, code):
    calls = []

    def fake_run_job(source, session_factory, settings, **kwargs):
        calls.append((source, kwargs["trigger"]))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(cli, "run_job", fake_run_job)
    monkeypatch.setattr(cli, "configure_logging", lambda *a: None)
    assert cli.main(["trello", "--trigger", "schedule"], session_factory=object()) == code
    assert calls == [("trello", "schedule")]


def test_cli_rejects_unknown_source():
    with pytest.raises(SystemExit):
        cli.main(["jira"], session_factory=object())


# --- URL webhook tidak boleh bocor lewat log httpx (review #34) --------------------------


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    quiet = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
    yield
    root.handlers[:], level = saved
    root.setLevel(level)
    for name, value in quiet.items():
        logging.getLogger(name).setLevel(value)


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
@pytest.mark.parametrize("fmt", ["json", "text"])
def test_webhook_url_is_not_written_to_log(restore_logging, capsys, fmt, level):
    configure_logging(fmt, level)
    s = settings(notify_webhook_url=WEBHOOK)

    assert send_notification(s, "berhasil", httpx.MockTransport(lambda r: httpx.Response(200)))

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"tidak bisa ke {request.url}")

    assert not send_notification(s, "gagal", httpx.MockTransport(unreachable))
    logging.getLogger("httpx").warning("peringatan httpx tetap tampil")

    output = capsys.readouterr().err
    assert "notifikasi gagal" in output  # log benar-benar tertangkap
    assert "peringatan httpx tetap tampil" in output
    assert "hooks.example.test" not in output
    assert "rahasia" not in output
