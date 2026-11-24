import type { Task, TaskStatus, TaskStatusInput } from './api';

/**
 * Aturan status task, sama dengan check_task_status_rules di backend (DIG-161) yang dicek ke
 * 1.200 task dataset dosbim:
 * - not_started: tanpa tanggal aktual
 * - in_progress, blocked, in_qa: wajib actual_start
 * - on_hold, dropped: actual_start boleh kosong
 * - hanya done yang punya actual_finish (wajib), dan hanya done yang boleh memenuhi DoD
 */
const NEEDS_START: readonly TaskStatus[] = ['in_progress', 'blocked', 'in_qa', 'done'];

type Values = Pick<Task, 'status' | 'actual_start' | 'actual_finish' | 'dod_fulfilled'>;
export type StatusErrors = Partial<Record<'actual_start' | 'actual_finish' | 'dod_fulfilled', string>>;

export function checkStatus(values: Values): StatusErrors {
  const errors: StatusErrors = {};
  const { status, actual_start: start, actual_finish: finish } = values;
  if (status === 'not_started' && start) errors.actual_start = 'Harus kosong untuk task yang belum dimulai';
  if (NEEDS_START.includes(status) && !start) errors.actual_start = 'Wajib diisi untuk status ini';
  if (status === 'done' && !finish) errors.actual_finish = 'Wajib diisi untuk task selesai';
  if (status !== 'done' && finish) errors.actual_finish = 'Harus kosong selama task belum selesai';
  if (start && finish && finish < start) errors.actual_finish = 'Tidak boleh lebih awal dari tanggal mulai aktual';
  if (values.dod_fulfilled && status !== 'done') errors.dod_fulfilled = 'Definition of Done hanya untuk task selesai';
  return errors;
}

/**
 * Perubahan untuk "ubah status cepat" (DIG-163): status baru plus tanggal yang otomatis
 * diisi atau dikosongkan supaya lolos aturan di atas. Tanggal yang sudah ada dipertahankan.
 */
export function quickChange(task: Values, next: TaskStatus, today: string): TaskStatusInput {
  const change: TaskStatusInput = { status: next };
  if (next === 'not_started') {
    if (task.actual_start) change.actual_start = null;
  } else if (NEEDS_START.includes(next) && !task.actual_start) {
    change.actual_start = today;
  }
  if (next === 'done') {
    // Tanggal selesai tidak boleh sebelum tanggal mulai, walau mulainya tercatat setelah hari ini.
    const start = change.actual_start ?? task.actual_start ?? today;
    if (!task.actual_finish) change.actual_finish = start > today ? start : today;
  } else {
    if (task.actual_finish) change.actual_finish = null;
    if (task.dod_fulfilled) change.dod_fulfilled = false;
  }
  return change;
}
