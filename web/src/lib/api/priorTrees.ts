/**
 * Prior tree endpoints.
 *
 * Every call that needs the building stock sends the semantic fields as the
 * editor currently has them -- the backend applies their transformation rules to
 * the project's GIS rows itself, so the browser never ships a copy of the data.
 */

import type { SemanticField } from '../types/semanticFields';
import type {
  ConditionPreview,
  ConditioningFieldsResponse,
  GeneratedPrior,
  GenerationMethod,
  PriorConfig,
  PriorValidation,
  SampleSummary,
  ScenarioPreview,
  ScenarioTarget,
} from '../types/priorTrees';

async function requestJson<T>(input: string, body: unknown): Promise<T> {
  const response = await fetch(input, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail ?? `Request to ${input} failed (${response.status}).`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json() as Promise<T>;
}

/** The semantic fields in the shape the backend's `SemanticField` model expects. */
function toApiFields(fields: SemanticField[]) {
  return fields.map((field) => ({
    id: field.id,
    name: field.name,
    type: field.type,
    data_type: field.dataType,
    options: field.options,
    description: field.description,
    requires_prior: field.requiresPrior,
    transformation_rule: field.transformationRule
      ? {
          id: field.transformationRule.id,
          type: field.transformationRule.type,
          source_column: field.transformationRule.sourceColumn,
          target_field: field.transformationRule.targetField,
          numeric_ranges: field.transformationRule.numericRanges,
          categorical_groups: field.transformationRule.categoricalGroups?.map((group) => ({
            group_label: group.groupLabel,
            source_values: group.sourceValues,
          })),
        }
      : null,
  }));
}

/** Every field a prior can condition on, with its distribution across the GIS rows. */
export function fetchConditioningFields(
  fields: SemanticField[]
): Promise<ConditioningFieldsResponse> {
  return requestJson('/api/prior-trees/fields', { fields: toApiFields(fields) });
}

/** How many lookup-table rows a choice of conditioning fields would produce. */
export function previewConditioning(
  fields: SemanticField[],
  conditionOn: string[]
): Promise<ConditionPreview> {
  return requestJson('/api/prior-trees/condition-preview', {
    fields: toApiFields(fields),
    condition_on: conditionOn,
  });
}

export interface GenerateOptions {
  target: string;
  targetValues: string[];
  conditionOn: string[];
  method: GenerationMethod;
  observedColumn?: string | null;
  dtype?: 'categorical' | 'numeric';
  minCount?: number;
}

export function generatePrior(
  fields: SemanticField[],
  options: GenerateOptions
): Promise<GeneratedPrior> {
  return requestJson('/api/prior-trees/generate', {
    fields: toApiFields(fields),
    target: options.target,
    target_values: options.targetValues,
    condition_on: options.conditionOn,
    method: options.method,
    observed_column: options.observedColumn ?? null,
    dtype: options.dtype ?? 'categorical',
    ...(options.minCount === undefined ? {} : { min_count: options.minCount }),
  });
}

/** Registry entries for fields the config references but hasn't declared yet. */
export async function fetchRegistrySuggestions(
  fields: SemanticField[],
  config: PriorConfig
): Promise<PriorConfig['registry']['fields']> {
  const data = await requestJson<{ fields: PriorConfig['registry']['fields'] }>(
    '/api/prior-trees/registry-suggestions',
    { fields: toApiFields(fields), config }
  );
  return data.fields;
}

export function validatePriorTree(
  config: PriorConfig,
  requiredTargets: string[]
): Promise<PriorValidation> {
  return requestJson('/api/prior-trees/validate', {
    config,
    required_targets: requiredTargets,
    fields: [],
  });
}

/** Draw `n` buildings from the config, over the project's own stock where possible. */
export function samplePriorTree(
  fields: SemanticField[],
  config: PriorConfig,
  n: number,
  seed: number | null
): Promise<SampleSummary> {
  return requestJson('/api/prior-trees/sample', {
    fields: toApiFields(fields),
    config,
    n,
    seed,
  });
}

/** Features a scenario can override or branch on, with their declared values. */
export async function fetchScenarioTargets(config: PriorConfig): Promise<ScenarioTarget[]> {
  const data = await requestJson<{ targets: ScenarioTarget[] }>(
    '/api/prior-trees/scenario-targets',
    { config, required_targets: [], fields: [] }
  );
  return data.targets;
}

/** Sample one baseline and apply every scenario to it. */
export function previewScenarios(
  fields: SemanticField[],
  config: PriorConfig,
  n: number,
  seed: number | null
): Promise<ScenarioPreview> {
  return requestJson('/api/prior-trees/scenarios/preview', {
    fields: toApiFields(fields),
    config,
    n,
    seed,
  });
}

export async function exportPriorTreeYaml(config: PriorConfig): Promise<string> {
  const response = await fetch('/api/prior-trees/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config, required_targets: [], fields: [] }),
  });
  if (!response.ok) throw new Error('Failed to export the prior tree.');
  return response.text();
}
