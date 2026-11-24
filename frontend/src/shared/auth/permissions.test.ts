import { describe, expect, it } from 'vitest';
import { navigation } from '../../app/navigation';
import { dataViews } from '../../modules/data/views';
import { allowed, can, PERM } from './permissions';

// Matriks peran dari backend/app/modules/auth/permissions.py (seed migrasi 0016).
const ROLE = {
  kaur_asman: ['master_data:read', 'baseline:read', 'workload:read_all', 'workload:read_own', 'change_event:write', 'availability:write'],
  system_analyst: ['master_data:read', 'baseline:read', 'workload:read_all', 'workload:read_own', 'change_event:write', 'availability:write', 'data_quality:read', 'event_log:export'],
  anggota_tim: ['master_data:read', 'workload:read_own', 'change_event:write_own'],
  admin_data: ['master_data:read', 'master_data:write', 'import:run', 'data_quality:read', 'event_log:export'],
  admin_it: ['user:manage'],
};
const user = (permissions: string[]) => ({ permissions });
const menu = (permissions: string[]) => allowed(navigation, user(permissions)).map((item) => item.label);
// Tab "Task saya" dites sendiri di bawah, supaya daftar tab master data tetap ringkas.
const MY_TASKS = 'task-saya';
const allTabs = (permissions: string[]) => allowed(dataViews, user(permissions)).map((item) => item.key);
const tabs = (permissions: string[]) => allTabs(permissions).filter((key) => key !== MY_TASKS);

describe('can', () => {
  it('true hanya untuk izin yang dipegang', () => {
    expect(can(user(ROLE.admin_data), PERM.masterDataWrite)).toBe(true);
    expect(can(user(ROLE.kaur_asman), PERM.masterDataWrite)).toBe(false);
  });

  it.each([null, undefined, {}, { permissions: [] }])('pengguna tanpa izin: %o', (value) => {
    expect(can(value, PERM.masterDataRead)).toBe(false);
  });
});

describe('menu per peran (FR-12)', () => {
  it('Kaur/Asman dan System Analyst melihat semua halaman', () => {
    expect(menu(ROLE.kaur_asman)).toEqual(['Data', 'Digital Twin', 'Simulasi', 'Evaluasi']);
    expect(menu(ROLE.system_analyst)).toEqual(['Data', 'Digital Twin', 'Simulasi', 'Evaluasi']);
  });

  it('anggota tim dan admin data hanya melihat Data', () => {
    expect(menu(ROLE.anggota_tim)).toEqual(['Data']);
    expect(menu(ROLE.admin_data)).toEqual(['Data']);
  });

  it('Admin IT dan akun tanpa peran tidak melihat menu', () => {
    expect(menu(ROLE.admin_it)).toEqual([]);
    expect(menu([])).toEqual([]);
  });

  it('dua peran digabung', () => {
    expect(menu([...ROLE.admin_data, ...ROLE.system_analyst])).toEqual(['Data', 'Digital Twin', 'Simulasi', 'Evaluasi']);
  });
});

describe('tab Data per peran', () => {
  const master = ['proyek', 'anggota', 'peran', 'task', 'kompleksitas', 'libur'];

  it('Kaur/Asman: master data, beban, dan ketersediaan, tanpa impor', () => {
    expect(tabs(ROLE.kaur_asman)).toEqual(['proyek', 'anggota', 'peran', 'task', 'beban', 'perubahan', 'kompleksitas', 'ketersediaan', 'libur']);
  });

  it('anggota tim: master data saja', () => {
    expect(tabs(ROLE.anggota_tim)).toEqual(master);
  });

  it('admin data: master data, alias identitas, impor, kualitas data, dan pemetaan Trello', () => {
    expect(tabs(ROLE.admin_data)).toEqual([...master, 'alias', 'impor', 'kualitas', 'trello']);
  });

  it('tab Kualitas data mengikuti izin data_quality:read (DIG-147)', () => {
    expect(tabs(ROLE.system_analyst)).toContain('kualitas');
    for (const role of [ROLE.kaur_asman, ROLE.anggota_tim]) expect(tabs(role)).not.toContain('kualitas');
  });
});

describe('tab Task saya (DIG-155)', () => {
  it('tampil untuk peran yang punya beban sendiri, paling akhir', () => {
    for (const role of [ROLE.anggota_tim, ROLE.kaur_asman, ROLE.system_analyst]) expect(allTabs(role).at(-1)).toBe(MY_TASKS);
  });

  it('tidak tampil untuk admin data', () => {
    expect(allTabs(ROLE.admin_data)).not.toContain(MY_TASKS);
  });
});
