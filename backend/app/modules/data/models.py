"""Model final sources D-01 s.d. D-11 (Data Dictionary bersama J&C dan tWinner).

Nama tabel dan kolom mengikuti Data Dictionary apa adanya karena tWinner membaca
tabel yang sama. Tabel internal J&C (staging, alias, event log, kualitas data,
audit) tidak ditaruh di sini.
"""

from datetime import date
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, Double, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.data.enums import (
    COMPLEXITY_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RESOURCE_ID_PATTERN,
    ROLE_ID_PATTERN,
    SECONDARY_ROLE_IDS_PATTERN,
    ProjectStatus,
    Seniority,
)


def one_of(column: str, values: type[StrEnum]) -> str:
    """Ekspresi CHECK `kolom IN (...)` dari sebuah StrEnum."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"


def matches(column: str, pattern: str) -> str:
    """Ekspresi CHECK regex PostgreSQL untuk format ID."""
    return f"{column} ~ '{pattern}'"


class Project(Base):
    """D-01 projects"""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(matches("project_id", PROJECT_ID_PATTERN), name="project_id_format"),
        CheckConstraint(one_of("status", ProjectStatus), name="status_valid"),
        CheckConstraint("priority_rank >= 1", name="priority_rank_min"),
        CheckConstraint("target_launch_date >= start_date", name="target_after_start"),
        CheckConstraint("actual_launch_date >= start_date", name="actual_after_start"),
    )

    project_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(200))
    process_owner: Mapped[str] = mapped_column(String(200))
    priority_rank: Mapped[int]
    start_date: Mapped[date] = mapped_column(Date)
    target_launch_date: Mapped[date] = mapped_column(Date)
    actual_launch_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    dor_fulfilled: Mapped[bool] = mapped_column(server_default=false())


class Role(Base):
    """D-03 roles"""

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(matches("role_id", ROLE_ID_PATTERN), name="role_id_format"),
        CheckConstraint("capacity_reference > 0", name="capacity_reference_positive"),
    )

    role_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    role_name: Mapped[str] = mapped_column(String(100))
    capacity_reference: Mapped[float] = mapped_column(Double, server_default="3.0")
    description: Mapped[str | None] = mapped_column(Text)


class Resource(Base):
    """D-02 resources

    secondary_role_ids tetap string berpemisah titik koma sesuai Data Dictionary.
    PostgreSQL tidak bisa memasang FK pada isi string, jadi CHECK hanya menjaga
    formatnya. Keberadaan setiap role_id diperiksa di service (DIG-100).
    """

    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint(matches("resource_id", RESOURCE_ID_PATTERN), name="resource_id_format"),
        CheckConstraint(
            matches("secondary_role_ids", SECONDARY_ROLE_IDS_PATTERN),
            name="secondary_role_ids_format",
        ),
        CheckConstraint(one_of("seniority", Seniority), name="seniority_valid"),
    )

    resource_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    resource_name: Mapped[str] = mapped_column(String(200))
    primary_role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"), index=True)
    secondary_role_ids: Mapped[str | None] = mapped_column(String(200))
    cross_role_capable: Mapped[bool] = mapped_column(server_default=false())
    join_date: Mapped[date] = mapped_column(Date)
    seniority: Mapped[str] = mapped_column(String(10))


class ComplexityLevel(Base):
    """D-04 complexity_levels"""

    __tablename__ = "complexity_levels"
    __table_args__ = (
        CheckConstraint(
            matches("complexity_id", COMPLEXITY_ID_PATTERN), name="complexity_id_format"
        ),
        CheckConstraint("min_days >= 0", name="min_days_min"),
        CheckConstraint("max_days >= min_days", name="max_days_after_min"),
        CheckConstraint("load_weight >= 0", name="load_weight_min"),
    )

    complexity_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    complexity_name: Mapped[str] = mapped_column(String(50))
    min_days: Mapped[float] = mapped_column(Double)
    max_days: Mapped[float] = mapped_column(Double)
    load_weight: Mapped[float] = mapped_column(Double)


class Holiday(Base):
    """D-11 holidays"""

    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, primary_key=True)
    holiday_name: Mapped[str] = mapped_column(String(200))
