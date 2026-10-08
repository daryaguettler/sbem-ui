export type FieldKind = 'string' | 'number' | 'boolean' | 'enum' | 'relation' | 'raw';

export interface ComponentFieldDescriptor {
  name: string;
  title: string;
  required: boolean;
  kind: FieldKind;
  options?: string[];
  relationType?: string;
  ge?: number;
  gt?: number;
  le?: number;
  lt?: number;
}

export interface ComponentTypeSchema {
  type: string;
  fields: ComponentFieldDescriptor[];
}

export type ComponentRecord = Record<string, unknown> & { Name: string };

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail ?? `Request to ${input} failed (${response.status}).`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function fetchComponentTypes(): Promise<{ types: string[] }> {
  return requestJson('/api/component-library/types');
}

export function fetchComponentSchema(componentType: string): Promise<ComponentTypeSchema> {
  return requestJson(`/api/component-library/schema/${encodeURIComponent(componentType)}`);
}

export async function fetchComponentRecords(componentType: string): Promise<ComponentRecord[]> {
  const { records } = await requestJson<{ records: ComponentRecord[] }>(
    `/api/component-library/${encodeURIComponent(componentType)}/records`
  );
  return records;
}

export function fetchComponentRecord(componentType: string, name: string): Promise<ComponentRecord> {
  return requestJson(
    `/api/component-library/${encodeURIComponent(componentType)}/records/${encodeURIComponent(name)}`
  );
}

export function createComponentRecord(
  componentType: string,
  payload: Record<string, unknown>
): Promise<ComponentRecord> {
  return requestJson(`/api/component-library/${encodeURIComponent(componentType)}/records`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updateComponentRecord(
  componentType: string,
  name: string,
  payload: Record<string, unknown>
): Promise<ComponentRecord> {
  return requestJson(
    `/api/component-library/${encodeURIComponent(componentType)}/records/${encodeURIComponent(name)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
}

export async function deleteComponentRecord(componentType: string, name: string): Promise<void> {
  await requestJson(
    `/api/component-library/${encodeURIComponent(componentType)}/records/${encodeURIComponent(name)}`,
    { method: 'DELETE' }
  );
}

export async function checkComponentExistence(
  componentType: string,
  names: string[]
): Promise<Record<string, boolean>> {
  if (names.length === 0) return {};
  const { existence } = await requestJson<{ existence: Record<string, boolean> }>(
    `/api/component-library/${encodeURIComponent(componentType)}/check-existence`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    }
  );
  return existence;
}
