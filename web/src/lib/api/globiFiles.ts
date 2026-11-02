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
  globiRoot: string;
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
