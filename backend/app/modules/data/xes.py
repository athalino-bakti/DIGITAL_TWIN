"""Serializer event log ke XES (DIG-172, story DIG-39), murni tanpa basis data.

Struktur mengikuti XML Schema XES (IEEE 1849): `log` berisi `extension`, `global`, `classifier`,
atribut log, lalu `trace`; tanpa target namespace. Ekstensi dan key diambil dari berkas resmi
xes-standard.org (concept, time, lifecycle, org).

Satu case = satu task (`event_log.case_id` = `task_id`, lihat `event_log_models`). Setiap event
adalah kejadian sesaat (action Trello atau kejadian D-10), jadi `lifecycle:transition` diisi
`complete` menurut model lifecycle standar.

Keluaran berupa generator potongan teks: satu trace dibangun lalu dilepas, sehingga ekspor
besar tidak dimuat seluruhnya ke memori. Escape XML dikerjakan `xml.etree.ElementTree` dan
`xml.sax.saxutils`.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.sax.saxutils import quoteattr

# Nilai atribut root. xes.version bertipe xs:decimal di XML Schema XES.
XES_VERSION = "2.0"
XES_FEATURES = ""

EXTENSIONS = (
    ("Concept", "concept", "http://www.xes-standard.org/concept.xesext"),
    ("Time", "time", "http://www.xes-standard.org/time.xesext"),
    ("Lifecycle", "lifecycle", "http://www.xes-standard.org/lifecycle.xesext"),
    ("Organizational", "org", "http://www.xes-standard.org/org.xesext"),
)
TRANSITION = "complete"
UNKNOWN = "__INVALID__"
EPOCH = "1970-01-01T00:00:00.000+00:00"


@dataclass(frozen=True)
class XesEvent:
    """Satu baris event_log yang sudah dibaca, ditambah peran pelaku bila diketahui."""

    case_id: str
    activity: str
    event_time: datetime
    project_id: str | None = None
    activity_kind: str | None = None
    resource_id: str | None = None
    actor_name: str | None = None
    role_id: str | None = None
    source: str | None = None
    source_ref: str | None = None
    event_id: int = 0


def timestamp(value: datetime) -> str:
    """xs:dateTime dengan zona waktu; waktu tanpa zona ditolak agar tidak salah tafsir."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("event_time wajib memiliki zona waktu")
    return value.isoformat(timespec="milliseconds")


def _attr(parent: Element, kind: str, key: str, value: str | None) -> None:
    if value is not None and value != "":
        SubElement(parent, kind, key=key, value=value)


def _header() -> str:
    log = Element("log")
    for name, prefix, uri in EXTENSIONS:
        SubElement(log, "extension", name=name, prefix=prefix, uri=uri)
    trace_global = SubElement(log, "global", scope="trace")
    _attr(trace_global, "string", "concept:name", UNKNOWN)
    event_global = SubElement(log, "global", scope="event")
    _attr(event_global, "string", "concept:name", UNKNOWN)
    _attr(event_global, "date", "time:timestamp", EPOCH)
    _attr(event_global, "string", "lifecycle:transition", TRANSITION)
    SubElement(log, "classifier", name="Activity", keys="concept:name")
    _attr(log, "string", "concept:name", "Digital Twin PuTI event log")
    _attr(log, "string", "lifecycle:model", "standard")
    body = "".join(tostring(child, encoding="unicode") for child in log)
    attrs = f"xes.version={quoteattr(XES_VERSION)}"
    if XES_FEATURES:
        attrs += f" xes.features={quoteattr(XES_FEATURES)}"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<log {attrs}>{body}'


def _trace(case_id: str, events: list[XesEvent]) -> str:
    trace = Element("trace")
    _attr(trace, "string", "concept:name", case_id)
    _attr(trace, "string", "project_id", next((e.project_id for e in events if e.project_id), None))
    for item in sorted(events, key=lambda e: (e.event_time, e.event_id)):
        event = SubElement(trace, "event")
        _attr(event, "string", "concept:name", item.activity)
        _attr(event, "string", "lifecycle:transition", TRANSITION)
        _attr(event, "date", "time:timestamp", timestamp(item.event_time))
        _attr(event, "string", "org:resource", item.resource_id or item.actor_name)
        _attr(event, "string", "org:role", item.role_id)
        _attr(event, "string", "activity_kind", item.activity_kind)
        _attr(event, "string", "source", item.source)
        _attr(event, "string", "source_ref", item.source_ref)
    return tostring(trace, encoding="unicode")


def serialize(events: Iterable[XesEvent]) -> Iterator[str]:
    """Dokumen XES sebagai potongan teks.

    `events` wajib sudah urut per `case_id` (event satu case berdampingan); di dalam case,
    event diurutkan ulang menurut `time:timestamp`.
    """
    yield _header()
    for case_id, group in groupby(events, key=lambda e: e.case_id):
        yield _trace(case_id, list(group))
    yield "</log>\n"


def to_xes(events: Iterable[XesEvent]) -> str:
    return "".join(serialize(events))
