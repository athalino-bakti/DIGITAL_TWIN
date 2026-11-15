"""Log terstruktur untuk job impor (DIG-128).

Dengan LOG_FORMAT=json setiap baris log menjadi satu objek JSON, sehingga mudah dicari dan
dihitung oleh alat pemantau (journalctl, Loki, CloudWatch, dan sejenisnya). Field tambahan
dikirim lewat `extra=`, misalnya `logger.info("job selesai", extra={"job_id": 7})`.
"""

import json
import logging
import sys
from datetime import UTC, datetime

# Atribut bawaan LogRecord; selain ini dianggap field tambahan dari `extra=`.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extra = {k: v for k, v in vars(record).items() if k not in _STANDARD}
        return f"{line} {extra}" if extra else line


def configure_logging(fmt: str = "text", level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
