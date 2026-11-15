"""Schema API graf dependency dan jalur kritis, tab Dependency (DIG-42, DIG-182)."""

from datetime import date

from pydantic import BaseModel, Field

from app.modules.data.enums import DependencyType, TaskPhase, TaskStatus


class DependencyNode(BaseModel):
    task_id: str
    task_name: str
    feature_name: str
    phase: TaskPhase
    status: TaskStatus
    estimated_days: float
    planned_start: date
    planned_finish: date
    earliest_start: float = Field(description="Hari kerja ke- sejak awal proyek (CPM)")
    earliest_finish: float
    latest_start: float
    latest_finish: float
    total_float: float = Field(description="Kelonggaran: hari yang boleh mundur tanpa geser proyek")
    is_critical: bool
    is_late: bool
    delay_working_days: int
    impact_days: float | None = Field(
        description="Estimasi dampak dari task terpilih; null bila tidak terdampak"
    )


class DependencyEdge(BaseModel):
    dependency_id: str
    depends_on_task_id: str = Field(description="Task prasyarat (asal panah)")
    task_id: str = Field(description="Task yang bergantung (ujung panah)")
    dependency_type: DependencyType
    propagation_factor: float
    is_critical: bool = Field(description="Menghubungkan dua task berurutan di jalur kritis")


class DependencyFocus(BaseModel):
    task_id: str
    delay_days: float = Field(description="Keterlambatan yang dirambatkan (hari kerja)")
    affected_count: int


class DependencyGraph(BaseModel):
    project_id: str
    project_name: str
    as_of: date
    project_duration: float = Field(description="Panjang jalur kritis dalam hari kerja")
    critical_task_ids: list[str] = Field(description="Task di jalur kritis, urut mulai paling awal")
    cycle_task_ids: list[str] = Field(
        description="Task yang dependency-nya melingkar; bila ada, CPM tidak dihitung"
    )
    focus: DependencyFocus | None
    nodes: list[DependencyNode]
    edges: list[DependencyEdge]
