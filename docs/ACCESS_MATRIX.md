# Matriks akses per peran (DIG-207)

Dibuat otomatis dari kode dengan `python -m app.qa.access_matrix --write ../docs/ACCESS_MATRIX.md` (dari folder backend). Setiap baris diuji lewat HTTP untuk kelima peran dan tanpa login di `tests/test_access_matrix.py`.

Keterangan: ✓ boleh, – ditolak 403. Endpoint selain publik menolak permintaan tanpa login dengan 401. Pada heatmap, peran dengan `workload:read_own` saja hanya melihat dirinya; pada daftar task, Anggota Tim hanya melihat task miliknya (DIG-19).

| Method | Endpoint | Izin | Kaur/Asman | System Analyst | Anggota Tim Pengembang | Administrator Data | Admin IT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/auth/login` | publik | ✓ | ✓ | ✓ | ✓ | ✓ |
| GET | `/auth/me` | login | ✓ | ✓ | ✓ | ✓ | ✓ |
| GET | `/data/audit-log` | `data_quality:read` | – | ✓ | – | ✓ | – |
| GET | `/data/availability` | `workload:read_all` | ✓ | ✓ | – | – | – |
| POST | `/data/availability` | `availability:write` | ✓ | ✓ | – | – | – |
| PATCH | `/data/availability/{availability_id}` | `availability:write` | ✓ | ✓ | – | – | – |
| DELETE | `/data/availability/{availability_id}` | `availability:write` | ✓ | ✓ | – | – | – |
| GET | `/data/availability/{availability_id}/affected-tasks` | `workload:read_all` | ✓ | ✓ | – | – | – |
| GET | `/data/change-events` | `workload:read_all` | ✓ | ✓ | – | – | – |
| POST | `/data/change-events` | `change_event:write` | ✓ | ✓ | – | – | – |
| GET | `/data/change-events/{event_id}` | `workload:read_all` | ✓ | ✓ | – | – | – |
| PATCH | `/data/change-events/{event_id}` | `change_event:write` | ✓ | ✓ | – | – | – |
| DELETE | `/data/change-events/{event_id}` | `change_event:write` | ✓ | ✓ | – | – | – |
| GET | `/data/complexity-levels` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| PATCH | `/data/complexity-levels/{complexity_id}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/event-log` | `event_log:export` | – | ✓ | – | ✓ | – |
| GET | `/data/event-log.xes` | `event_log:export` | – | ✓ | – | ✓ | – |
| POST | `/data/event-log/rebuild` | `import:run` | – | – | – | ✓ | – |
| GET | `/data/holidays` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| POST | `/data/holidays` | `master_data:write` | – | – | – | ✓ | – |
| PATCH | `/data/holidays/{holiday_date}` | `master_data:write` | – | – | – | ✓ | – |
| DELETE | `/data/holidays/{holiday_date}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/import-jobs` | `data_quality:read` | – | ✓ | – | ✓ | – |
| GET | `/data/import-jobs/{job_id}` | `data_quality:read` | – | ✓ | – | ✓ | – |
| POST | `/data/imports/project-plan` | `import:run` | – | – | – | ✓ | – |
| GET | `/data/my-tasks` | `workload:read_own` | ✓ | ✓ | ✓ | – | – |
| POST | `/data/my-tasks/{task_id}/events` | `change_event:write_own` | – | – | ✓ | – | – |
| POST | `/data/my-tasks/{task_id}/events/{event_id}/resolve` | `change_event:write_own` | – | – | ✓ | – | – |
| POST | `/data/overrun-detection` | `change_event:write` | ✓ | ✓ | – | – | – |
| GET | `/data/projects` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| POST | `/data/projects` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/projects/{project_id}` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| PATCH | `/data/projects/{project_id}` | `master_data:write` | – | – | – | ✓ | – |
| DELETE | `/data/projects/{project_id}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/quality/rejected-rows` | `data_quality:read` | – | ✓ | – | ✓ | – |
| GET | `/data/quality/rejected-rows.csv` | `data_quality:read` | – | ✓ | – | ✓ | – |
| GET | `/data/quality/summary` | `data_quality:read` | – | ✓ | – | ✓ | – |
| GET | `/data/quality/summary.csv` | `data_quality:read` | – | ✓ | – | ✓ | – |
| GET | `/data/resource-aliases` | `master_data:write` | – | – | – | ✓ | – |
| POST | `/data/resource-aliases` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/resource-aliases/unmapped` | `master_data:write` | – | – | – | ✓ | – |
| PATCH | `/data/resource-aliases/{alias_id}` | `master_data:write` | – | – | – | ✓ | – |
| DELETE | `/data/resource-aliases/{alias_id}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/resources` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| POST | `/data/resources` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/resources/{resource_id}` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| PATCH | `/data/resources/{resource_id}` | `master_data:write` | – | – | – | ✓ | – |
| DELETE | `/data/resources/{resource_id}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/roles` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| PATCH | `/data/roles/{role_id}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/data/tasks` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| GET | `/data/tasks/{task_id}` | `master_data:read` | ✓ | ✓ | ✓ | ✓ | – |
| GET | `/data/tasks/{task_id}/assignments` | `workload:read_all` | ✓ | ✓ | – | – | – |
| GET | `/data/tasks/{task_id}/replacement-candidates` | `workload:read_all` | ✓ | ✓ | – | – | – |
| PATCH | `/data/tasks/{task_id}/status` | `master_data:write` | – | – | – | ✓ | – |
| POST | `/data/tasks/{task_id}/takeover` | `availability:write` | ✓ | ✓ | – | – | – |
| GET | `/data/trello-lists` | `import:run` | – | – | – | ✓ | – |
| PATCH | `/data/trello-lists/{board_id}/{list_id}` | `import:run` | – | – | – | ✓ | – |
| GET | `/data/workload-items` | `workload:read_all` | ✓ | ✓ | – | – | – |
| POST | `/data/workload-items` | `master_data:write` | – | – | – | ✓ | – |
| POST | `/data/workload-items/import` | `import:run` | – | – | – | ✓ | – |
| PATCH | `/data/workload-items/{item_id}` | `master_data:write` | – | – | – | ✓ | – |
| DELETE | `/data/workload-items/{item_id}` | `master_data:write` | – | – | – | ✓ | – |
| GET | `/digital-twin/dependency` | `baseline:read` | ✓ | ✓ | – | – | – |
| GET | `/digital-twin/process-map` | `baseline:read` | ✓ | ✓ | – | – | – |
| GET | `/digital-twin/summary` | `baseline:read` | ✓ | ✓ | – | – | – |
| GET | `/digital-twin/timeline` | `baseline:read` | ✓ | ✓ | – | – | – |
| GET | `/digital-twin/workload-heatmap` | `workload:read_all` atau `workload:read_own` | ✓ | ✓ | ✓ | – | – |
| GET | `/health` | publik | ✓ | ✓ | ✓ | ✓ | ✓ |
| GET | `/health/ready` | publik | ✓ | ✓ | ✓ | ✓ | ✓ |
