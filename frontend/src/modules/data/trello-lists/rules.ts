import type { Mapping, TaskPhase, TaskStatus, TrelloList } from './api';

// Urutan penting: "Blocked QA" lebih dulu dianggap blocked, "Done testing" dianggap done.
const STATUS_RULES: [RegExp, TaskStatus][] = [
  [/block|hambat|stuck|kendala/, 'blocked'],
  [/hold|tunda|pending|pause|jeda/, 'on_hold'],
  [/drop|batal|cancel/, 'dropped'],
  [/done|selesai|complete|rilis|release|deploy|live|closed/, 'done'],
  [/\bqa\b|test|uji|review|uat|verif/, 'in_qa'],
  [/progress|doing|dikerjakan|sedang|\bwip\b|ongoing|develop/, 'in_progress'],
  [/to ?do|backlog|belum|antri|queue|ready|siap|icebox|baru/, 'not_started'],
];

const PHASE_RULES: [RegExp, TaskPhase][] = [
  [/bug|fix|perbaik/, 'bugfix'],
  [/\bui\b|\bux\b|ui\/ux|desain|design|mockup/, 'uiux'],
  [/\bqa\b|test|uji|uat/, 'testing'],
  [/dokumen|\bdocs?\b|documentation/, 'documentation'],
  [/frontend|front-end|\bfe\b/, 'fe_dev'],
  [/backend|back-end|\bbe\b|\bapi\b/, 'be_dev'],
  [/\bdm\b|data model|database|migra/, 'dm_dev'],
  [/plan|rencana|analisis|requirement|kebutuhan/, 'planning'],
];

const normalize = (name: string) => name.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();

/**
 * Usulan status dan phase dari nama list, hanya sebagai isian awal yang tetap disimpan manual.
 * Nama list PuTI belum diketahui, jadi aturannya dibuat umum (bahasa Indonesia dan Inggris).
 */
export function suggestMapping(listName: string): Mapping {
  const name = normalize(listName);
  return {
    status: STATUS_RULES.find(([pattern]) => pattern.test(name))?.[1] ?? null,
    phase: PHASE_RULES.find(([pattern]) => pattern.test(name))?.[1] ?? null,
  };
}

export const listKey = (list: Pick<TrelloList, 'board_id' | 'list_id'>) => `${list.board_id}/${list.list_id}`;

export const sameMapping = (a: Mapping, b: Mapping) => a.status === b.status && a.phase === b.phase;

/** List dikelompokkan per papan, papan dengan list belum dipetakan lebih dulu. */
export function groupByBoard(lists: readonly TrelloList[]): { board_id: string; board_name: string | null; lists: TrelloList[] }[] {
  const boards = new Map<string, { board_id: string; board_name: string | null; lists: TrelloList[] }>();
  for (const list of lists) {
    const board = boards.get(list.board_id) ?? { board_id: list.board_id, board_name: list.board_name, lists: [] };
    board.board_name ??= list.board_name;
    board.lists.push(list);
    boards.set(list.board_id, board);
  }
  const unmapped = (b: { lists: TrelloList[] }) => b.lists.filter((l) => l.status === null).length;
  return [...boards.values()].sort((a, b) => unmapped(b) - unmapped(a) || (a.board_name ?? a.board_id).localeCompare(b.board_name ?? b.board_id));
}
