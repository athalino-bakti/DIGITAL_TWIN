"""Schema heatmap beban kerja (DIG-188). Kontrak: KONTRAK_DIG-188_HEATMAP.md."""

from datetime import date

from pydantic import BaseModel, Field


class HeatmapWeek(BaseModel):
    week_start: date
    week_end: date
    working_days: int
    holidays: list[date]


class HeatmapCategory(BaseModel):
    code: str
    label: str
    min: float | None
    max: float | None
    overload: bool


class HeatmapSummary(BaseModel):
    week_start: date = Field(description="Senin minggu yang memuat as_of")
    overloaded: int = Field(description="Anggota dengan RLI > 1,00 pada minggu itu")
    resources: int


class HeatmapCell(BaseModel):
    week_start: date
    rli: float | None = Field(description="Dibulatkan 3 desimal; null bila kapasitas 0")
    category: str
    project_load: float
    non_project_load: float
    capacity: float
    available_days: int
    onboarding_factor: float
    tasks: int
    workload_items: int


class HeatmapRow(BaseModel):
    resource_id: str
    resource_name: str
    primary_role_id: str
    capacity_reference: float
    is_onboarding: bool
    cells: list[HeatmapCell]


class WorkloadHeatmap(BaseModel):
    as_of: date
    formula_version: str
    provisional: bool
    weeks: list[HeatmapWeek]
    categories: list[HeatmapCategory]
    summary: HeatmapSummary
    rows: list[HeatmapRow]
