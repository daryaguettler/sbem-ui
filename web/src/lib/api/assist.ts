/** AI drafting: describe a definition in plain language, get a checked draft back. */

export interface AssistStatus {
  available: boolean;
  reason: string | null;
}

/** A semantic field as the API sends it (snake_case); see utils/semanticFieldRules.fromApiField. */
export interface ApiSemanticField {
  id: string;
  name: string;
  type: 'deterministic' | 'stochastic';
  data_type: 'numeric' | 'categorical' | 'string';
  options: string[];
  description?: string | null;
  requires_prior?: boolean;
  transformation_rule?: {
    id: string;
    type: 'numeric_range' | 'categorical_mapping' | 'compound';
    source_column: string;
    target_field: string;
    numeric_ranges?: Array<{ min: number; max: number; label: string }> | null;
    categorical_groups?: Array<{ group_label: string; source_values: string[] }> | null;
  } | null;
}

export interface SemanticFieldDraft {
  field: ApiSemanticField;
  /** The model's own output, sent back as `previous` to refine it. */
  draft: Record<string, unknown>;
  assumptions: string[];
  questions: string[];
  errors: string[];
  warnings: string[];
  coverage: { mapped_percent: number; unmapped_count: number; total_count: number } | null;
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request to ${input} failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export function fetchAssistStatus(): Promise<AssistStatus> {
  return requestJson('/api/assist/status');
}

export function draftSemanticField(payload: {
  description: string;
  field_name?: string | null;
  field_id?: string | null;
  existing_fields: unknown[];
  previous?: Record<string, unknown> | null;
}): Promise<SemanticFieldDraft> {
  return requestJson('/api/assist/semantic-field', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
