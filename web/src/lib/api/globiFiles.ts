/**
 * globi's run files (building.yml for `globi simulate`; manifest.yml, artifacts.yml and
 * gis-preprocessor.yml for a batch run), generated from the project's saved files.
 */

export interface GlobiFilesStatus {
  /** From the saved semantic-fields.yaml: one building value is picked per field. */
  fields: Array<{ name: string; options: Array<string | number> }>;
  /** Project-relative weather .zip files (a template project ships one). */
  weather: string[];
  gisFile: string | null;
  componentMapSaved: boolean;
}

export interface BuildingGeometry {
  length: number;
  width: number;
  num_floors: number;
  f2f_height: number;
  wwr: number;
}

export interface GeneratedGlobiFiles {
  written: string[];
  warnings: string[];
  commands: { simulate: string; batch?: string };
  /** Where to run the commands: the globi checkout. */
  cwd: string;
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

export function fetchGlobiFilesStatus(): Promise<GlobiFilesStatus> {
  return requestJson('/api/globi-files/');
}

export function generateGlobiFiles(body: {
  name: string;
  epwzip_file: string;
  context: Record<string, string>;
  building: BuildingGeometry;
}): Promise<GeneratedGlobiFiles> {
  return requestJson('/api/globi-files/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// -- runs from Model Execution ----------------------------------------------------------

/** globi's Hatchet dashboard, where batch runs show their progress and task logs. */
// shortcut: globi's docker-compose port; make it a setting if Hatchet runs elsewhere
export const HATCHET_URL = 'http://localhost:8888';

/** End uses in kWh/m² by name (Heating, Cooling, Lighting, …). */
export type EndUses = Record<string, number>;

export interface BuildingRunResult {
  end_uses_kwh_m2: EndUses;
  peak_kw_m2: Record<string, number>;
  output_dir: string;
  /** The characteristics building.yml was generated with. */
  context: Record<string, string>;
}

export interface StockRun {
  /** Floor-area-weighted mean over the sample. */
  mean_kwh_m2: EndUses;
  buildings: Array<{ building_id: string; area_m2: number; values: Record<string, string>; end_uses_kwh_m2: EndUses }>;
  results_file: string;
  run_name: string;
}

export interface SampleRunResult {
  buildings: number;
  run_dir: string;
  /** By Scenario value; every scenario ran the same buildings. */
  scenarios: Record<string, StockRun>;
}

export interface RunJob<T> {
  id: string;
  /** interrupted: the backend restarted during the run, so its progress was lost. */
  status: 'running' | 'done' | 'failed' | 'interrupted';
  startedAt: string;
  stage: string;
  result: T | null;
  error: string | null;
}

/** Poll a background run until it ends, reporting each new stage. */
async function untilDone<T>(job: RunJob<T>, onStage: (stage: string) => void): Promise<T> {
  while (job.status === 'running') {
    onStage(job.stage);
    await new Promise((resolve) => setTimeout(resolve, 2000));
    job = await requestJson<RunJob<T>>(`/api/globi-files/jobs/${job.id}`);
  }
  if (job.status === 'failed' || job.result === null) throw new Error(job.error ?? 'The run failed.');
  return job.result;
}

/** Keep following a run that was started before this page loaded. */
export function resumeRun<T>(job: RunJob<T>, onStage: (stage: string) => void): Promise<T> {
  return untilDone(job, onStage);
}

/** The project's latest run of each kind (saved in its runs/ folder), or null if none yet. */
export function fetchLatestRuns(): Promise<{ building: RunJob<BuildingRunResult> | null; sample: RunJob<SampleRunResult> | null }> {
  return requestJson('/api/globi-files/runs');
}

/** The Scenario values that have a generated batch manifest. */
export async function fetchRunScenarios(): Promise<string[]> {
  return (await requestJson<{ scenarios: string[] }>('/api/globi-files/scenarios')).scenarios;
}

/** Simulate building.yml on this machine and resolve with its end uses. */
export async function runBuilding(onStage: (stage: string) => void): Promise<BuildingRunResult> {
  return untilDone(await requestJson<RunJob<BuildingRunResult>>('/api/globi-files/run-building', { method: 'POST' }), onStage);
}

/** Simulate n random buildings under each scenario on globi's local Hatchet. */
export async function runSample(n: number, scenarios: string[], onStage: (stage: string) => void): Promise<SampleRunResult> {
  const job = await requestJson<RunJob<SampleRunResult>>('/api/globi-files/run-sample', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ n, scenarios }),
  });
  return untilDone(job, onStage);
}
