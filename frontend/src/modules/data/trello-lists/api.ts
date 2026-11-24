import { apiGet, apiPatch, apiPost } from '../../../shared/api/client';

/** Tabel internal J&C trello_list_mapping (DIG-117, DIG-120). Hanya Administrator Data. */
export const TASK_STATUSES = ['not_started', 'in_progress', 'blocked', 'on_hold', 'in_qa', 'done', 'dropped'] as const;
export const TASK_PHASES = ['planning', 'uiux', 'dm_dev', 'be_dev', 'fe_dev', 'testing', 'bugfix', 'documentation'] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];
export type TaskPhase = (typeof TASK_PHASES)[number];

export type TrelloList = {
  board_id: string;
  board_name: string | null;
  list_id: string;
  list_name: string;
  status: TaskStatus | null;
  phase: TaskPhase | null;
  updated_at: string;
  actions: number;
  last_seen: string | null;
};

export type Mapping = { status: TaskStatus | null; phase: TaskPhase | null };

export type EventLogReport = {
  events: number;
  cases: number;
  skipped: Record<string, number>;
};

export const listTrelloLists = (signal?: AbortSignal) => apiGet<TrelloList[]>('/data/trello-lists', signal);
export const updateTrelloList = (list: Pick<TrelloList, 'board_id' | 'list_id'>, mapping: Mapping) =>
  apiPatch<TrelloList>(`/data/trello-lists/${list.board_id}/${list.list_id}`, mapping);
export const rebuildEventLog = () => apiPost<EventLogReport>('/data/event-log/rebuild', {});
