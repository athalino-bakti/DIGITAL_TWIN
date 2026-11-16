"""Schema API tab Process Map (DIG-169, story DIG-38)."""

from datetime import date

from pydantic import BaseModel, Field


class ProcessMapNode(BaseModel):
    id: str = Field(description="Nama aktivitas; unik dalam satu process map")
    label: str
    frequency: int = Field(description="Jumlah event aktivitas ini")
    cases: int = Field(description="Jumlah case (task) yang memuat aktivitas ini")
    start_cases: int = Field(description="Jumlah case yang diawali aktivitas ini")
    end_cases: int = Field(description="Jumlah case yang diakhiri aktivitas ini")


class ProcessMapEdge(BaseModel):
    source: str = Field(description="id node asal")
    target: str = Field(description="id node tujuan")
    frequency: int = Field(description="Berapa kali target langsung mengikuti source")
    cases: int = Field(description="Jumlah case yang memuat pasangan ini")
    mean_hours: float = Field(description="Rata-rata jeda source ke target, dalam jam")
    median_hours: float


class ActivityCount(BaseModel):
    activity: str
    cases: int


class HiddenCount(BaseModel):
    edges: int = Field(description="Edge yang disembunyikan karena di bawah min_frequency")
    nodes: int = Field(description="Node yang disembunyikan karena tidak lagi punya edge")
    edge_frequency: int = Field(description="Jumlah frekuensi edge yang disembunyikan")


class ProcessMapResponse(BaseModel):
    project_id: str | None
    date_from: date | None
    date_to: date | None
    activity_kinds: list[str]
    min_frequency: int
    event_log_events: int = Field(
        description="Seluruh baris event_log tanpa filter; 0 berarti event log belum dibentuk"
    )
    cases: int = Field(description="Case yang punya event setelah filter")
    events: int
    max_edge_frequency: int = Field(description="Frekuensi edge terbesar sebelum filter (slider)")
    nodes: list[ProcessMapNode]
    edges: list[ProcessMapEdge]
    start_activities: list[ActivityCount]
    end_activities: list[ActivityCount]
    hidden: HiddenCount
