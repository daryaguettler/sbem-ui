/**
 * Sampling: which buildings to simulate and how many draws of the estimated characteristics
 * each gets. Writing produces gis/buildings-sampled.geojson for globi's batch run.
 */

import type { SemanticField } from '../types/semanticFields';
import type { PriorConfig } from '../types/priorTrees';
import { toApiFields } from './priorTrees';

export interface SamplingSettings {
  draws: number;
  seed: number;
  buildings: { mode: 'all' | 'random' | 'stratified'; n: number; per_stratum: number; strata: string[] };
}

export interface SamplingSummary {
  totalBuildings: number;
  /** Buildings left out because they lack a value an estimate depends on. */
  skipped: number;
  buildings: number;
  strata: number | null;
  draws: number;
  simulations: number;
  estimated: string[];
  /** Set once written. */
  path?: string;
  rows?: number;
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail ?? `Request to ${input} failed (${response.status}).`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json() as Promise<T>;
}

export function fetchSamplingSettings(): Promise<SamplingSettings> {
  return requestJson('/api/sampling/');
}

function post(path: 'preview' | 'write', fields: SemanticField[], config: PriorConfig, settings: SamplingSettings) {
  return requestJson<SamplingSummary>(`/api/sampling/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields: toApiFields(fields), config, settings }),
  });
}

export const previewSampling = (fields: SemanticField[], config: PriorConfig, settings: SamplingSettings) =>
  post('preview', fields, config, settings);

export const writeSampling = (fields: SemanticField[], config: PriorConfig, settings: SamplingSettings) =>
  post('write', fields, config, settings);
