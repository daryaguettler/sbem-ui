/** Part rules endpoints, and the library check that resolves the buildings' combinations. */
import type { PartRules } from '../utils/partRules';

export interface PartInfo {
  path: string;
  type: string;
  group: string;
}

export interface CompileResult {
  ok: boolean;
  errors: string[];
  skipped?: boolean;
  groups?: Record<string, { fields: string[]; combinations: number }>;
  records?: number;
}

export interface LibraryCheck {
  ok: boolean;
  tested: number;
  failed: number;
  errors: string[];
  missing: Array<{ path: string; type: string; name: string; buildings: number }>;
  unmapped: Array<{ field: string; value: string; buildings: number }>;
  /** Buildings checked; 0 when there are none yet and every combination was checked. */
  buildings: number;
  source: string;
}

/** A stock-model template's ready-made characteristics (resstock-preset.yml). */
export interface StockPreset {
  source: { repo: string; tag: string };
  assumptions: string[];
  characteristics: Array<{ name: string; parts: string[]; options: Record<string, string> }>;
}

async function post<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: 'POST' });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail ?? 'Request failed.');
  return data as T;
}

export async function fetchStockPreset(): Promise<StockPreset | null> {
  const response = await fetch('/api/workspace/stock-preset');
  return response.ok ? (await response.json()).preset : null;
}

export async function fetchParts(): Promise<PartInfo[]> {
  const response = await fetch('/api/part-rules/parts');
  return response.ok ? (await response.json()).parts : [];
}

export const importRules = () => post<{ rules: PartRules; notes: string[] }>('/api/part-rules/import');
export const baselineRules = () => post<{ rules: PartRules }>('/api/part-rules/baseline');
export const checkLibrary = () => post<LibraryCheck>('/api/component-map/check');
