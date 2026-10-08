/**
 * The project's runner repo (norway-globi): validation, retrofit previews, sampling
 * estimates and small local test runs. Each call is a background job polled until done.
 */

export type RunnerCommand = 'validate' | 'retrofit-preview' | 'sampling' | 'test-run';

export interface RunnerJob<T = unknown> {
  id: string;
  command: RunnerCommand;
  status: 'running' | 'done' | 'failed';
  result: T | null;
  error: string | null;
}

export interface SamplingSettings {
  n_per_iter: number | number[] | null;
  min_per_stratum: number | null;
  max_iters: number | null;
  strata_fields: string[];
  strata_bins: Record<string, number[]>;
  context_per_stratum: number | null;
  partition_field: string | null;
  n_samples: number | null;
  packages: 'all' | string[];
}

/** Test runs are capped (local only); the backend and norway-globi enforce this too. */
export const MAX_TEST_BUILDINGS = 25;

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail ?? `Request to ${input} failed (${response.status}).`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json() as Promise<T>;
}

export function fetchRunnerStatus(): Promise<{ runner: string | null; available: boolean }> {
  return requestJson('/api/runner/status');
}

/** Start a job and resolve once it finishes (throws with the job's error if it fails). */
export async function runJob<T>(
  command: RunnerCommand,
  options: Record<string, unknown> = {}
): Promise<T> {
  let job = await requestJson<RunnerJob<T>>('/api/runner/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, options }),
  });
  while (job.status === 'running') {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    job = await requestJson<RunnerJob<T>>(`/api/runner/jobs/${job.id}`);
  }
  if (job.status === 'failed' || job.result === null) {
    throw new Error(job.error ?? `${command} failed`);
  }
  return job.result;
}

export function fetchSampling(): Promise<SamplingSettings> {
  return requestJson('/api/runner/sampling');
}

export function saveSampling(settings: Partial<SamplingSettings>): Promise<SamplingSettings> {
  return requestJson('/api/runner/sampling', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
}
