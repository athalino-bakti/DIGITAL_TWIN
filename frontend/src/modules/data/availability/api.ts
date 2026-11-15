import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client';

export const ABSENCE_TYPES = ['planned_leave', 'sudden_leave', 'maternity_leave', 'rotation_out', 'rotation_in'] as const;
export type AbsenceType = (typeof ABSENCE_TYPES)[number];

export const ABSENCE_LABEL: Record<AbsenceType, string> = {
  planned_leave: 'Cuti terencana',
  sudden_leave: 'Izin mendadak',
  maternity_leave: 'Cuti melahirkan',
  rotation_out: 'Rotasi keluar',
  rotation_in: 'Rotasi masuk',
};

/** D-09 availability, ditambah nama anggota dan hitungan hari dari server. */
export type Availability = {
  availability_id: string;
  resource_id: string;
  resource_name: string;
  date_start: string;
  date_end: string;
  absence_type: AbsenceType;
  is_known_at_planning: boolean;
  calendar_days: number;
  working_days: number;
};

export type AvailabilityInput = Pick<Availability, 'resource_id' | 'date_start' | 'date_end' | 'absence_type' | 'is_known_at_planning'> & { availability_id?: string };

/** D-11 holidays. */
export type Holiday = { holiday_date: string; holiday_name: string; is_weekend: boolean };

type AvailabilityQuery = { resource_id?: string; date_from?: string; date_to?: string };

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const listAvailability = (params: AvailabilityQuery, signal?: AbortSignal) => apiGet<Availability[]>(`/data/availability${query(params)}`, signal);
export const createAvailability = (input: AvailabilityInput) => apiPost<Availability>('/data/availability', input);
export const updateAvailability = (id: string, input: Partial<AvailabilityInput>) => apiPatch<Availability>(`/data/availability/${id}`, input);
export const deleteAvailability = (id: string) => apiDelete(`/data/availability/${id}`);

export const listHolidays = (year?: number, signal?: AbortSignal) => apiGet<Holiday[]>(`/data/holidays${query({ year })}`, signal);
export const createHoliday = (input: Omit<Holiday, 'is_weekend'>) => apiPost<Holiday>('/data/holidays', input);
export const updateHoliday = (date: string, holiday_name: string) => apiPatch<Holiday>(`/data/holidays/${date}`, { holiday_name });
export const deleteHoliday = (date: string) => apiDelete(`/data/holidays/${date}`);
