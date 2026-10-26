/**
 * Single building as a flat model: every parameter in one form, saved to the project's
 * flat-building.yml and simulated by globi (`make cli simulate-flat`, EnergyPlus in Docker).
 */

import { waitForJob, type RunnerJob } from './runner';

export interface FlatModelField {
  name: string;
  group: string;
  hint: string;
  type: 'number' | 'integer' | 'choice' | 'text';
  options?: string[];
  min?: number;
  max?: number;
  value: unknown;
}

export interface FlatModelForm {
  file: string;
  fields: FlatModelField[];
}

export interface FlatModelResult {
  end_uses_kwh_m2: Record<string, number>;
  peak_kw_m2: Record<string, number>;
  output_dir: string;
}

/** A failed request: `fields` maps field names to messages when the values are invalid. */
export class FlatModelError extends Error {
  constructor(
    message: string,
    public fields: Record<string, string> = {}
  ) {
    super(message);
  }
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new FlatModelError(detail?.message ?? `Request to ${input} failed (${response.status}).`, detail?.fields);
  }
  return response.json() as Promise<T>;
}

export function fetchFlatModel(): Promise<FlatModelForm> {
  return request('/api/flat-model');
}

export function saveFlatModel(values: Record<string, unknown>): Promise<FlatModelForm> {
  return request('/api/flat-model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
}

/** Simulate the saved building and resolve with its results. */
export async function runFlatModel(): Promise<FlatModelResult> {
  const job = await request<RunnerJob<FlatModelResult>>('/api/flat-model/run', { method: 'POST' });
  return waitForJob(job);
}
