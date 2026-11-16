import type { EventKind, MyTask, MyTaskEvent } from './api';

/** Tombol yang tersedia untuk satu task di daftar "Task saya" (DIG-155). */
export type TaskAction =
  | { kind: EventKind; mode: 'record'; label: string }
  | { kind: EventKind; mode: 'resolve'; label: string; event: MyTaskEvent };

// Status yang berarti task sedang dikerjakan; hanya ini yang berubah menjadi terhambat.
const BLOCKABLE = new Set(['in_progress', 'in_qa']);
// Hambatan bisa dicatat pada task yang sedang dikerjakan atau sudah terhambat. Task yang
// belum dimulai atau ditunda ditolak backend (409), jadi tombolnya tidak ditampilkan.
const CAN_BLOCK = new Set([...BLOCKABLE, 'blocked']);

export function actionsFor(task: MyTask): TaskAction[] {
  const actions: TaskAction[] = [];
  if (task.open_blocker) actions.push({ kind: 'blocker', mode: 'resolve', label: 'Hambatan selesai', event: task.open_blocker });
  else if (CAN_BLOCK.has(task.status)) actions.push({ kind: 'blocker', mode: 'record', label: 'Tandai terhambat' });
  if (task.open_overrun) actions.push({ kind: 'overrun', mode: 'resolve', label: 'Overrun selesai', event: task.open_overrun });
  else if (task.is_past_plan) actions.push({ kind: 'overrun', mode: 'record', label: 'Catat overrun' });
  return actions;
}

/** Penjelasan apa yang terjadi pada task, ditampilkan sebelum pengguna menyimpan. */
export function effectNote(task: MyTask, action: TaskAction): string {
  if (action.kind === 'overrun') {
    return action.mode === 'record'
      ? 'Task dicatat melewati rencana. Status task tidak berubah.'
      : 'Overrun ditandai selesai. Status task tidak berubah.';
  }
  if (action.mode === 'resolve') {
    return task.status === 'blocked'
      ? 'Hambatan ditandai selesai dan task kembali berstatus Dikerjakan.'
      : 'Hambatan ditandai selesai. Status task tidak berubah.';
  }
  if (BLOCKABLE.has(task.status)) return 'Hambatan dicatat dan status task berubah menjadi Terhambat.';
  return 'Hambatan dicatat. Task sudah berstatus Terhambat.';
}

/** Batas tanggal yang boleh dipilih: tidak di masa depan, dan selesai tidak sebelum kejadiannya. */
export function dateBounds(action: TaskAction, today: string): { min?: string; max: string } {
  return action.mode === 'resolve' ? { min: action.event.event_date, max: today } : { max: today };
}

/** Pesan kesalahan tanggal sebelum dikirim, atau null bila sah. */
export function checkDate(action: TaskAction, value: string, today: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Isi tanggal';
  if (value > today) return 'Tidak boleh tanggal yang akan datang';
  if (action.mode === 'resolve' && value < action.event.event_date) return 'Tidak boleh sebelum tanggal kejadian';
  return null;
}
