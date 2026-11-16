"""DIG-153: aturan kepemilikan task dan status sesudah blocker, tanpa basis data."""

from datetime import date

import pytest

from app.modules.data import my_task_service as service
from app.modules.data.enums import TaskStatus


@pytest.mark.parametrize(
    ("assigned", "released", "on", "expected"),
    [
        (date(2026, 3, 2), None, date(2026, 3, 2), True),
        (date(2026, 3, 2), None, date(2026, 3, 1), False),  # belum ditugaskan
        (date(2026, 3, 2), date(2026, 3, 10), date(2026, 3, 10), True),  # hari terakhir
        (date(2026, 3, 2), date(2026, 3, 10), date(2026, 3, 11), False),  # sudah dilepas
    ],
)
def test_is_active_assignment(assigned, released, on, expected):
    assert service.is_active_assignment(assigned, released, on) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("in_progress", "blocked"),
        ("in_qa", "blocked"),
        ("not_started", "not_started"),  # blocked wajib punya actual_start (DIG-161)
        ("on_hold", "on_hold"),
        ("blocked", "blocked"),
    ],
)
def test_status_after_blocker(status, expected):
    assert service.status_after_blocker(TaskStatus(status)) == expected
