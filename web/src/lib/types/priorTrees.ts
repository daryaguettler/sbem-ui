/**
 * Types for the prior tree editor.
 *
 * `PriorConfig` is a `semantic_priors.RegionConfig` -- the exact document the
 * sampling engine loads -- so the field names here are the YAML's snake_case
 * keys rather than the camelCase used elsewhere in the UI. Everything the
 * backend computes *about* a config (candidates, validation, samples) is
 * camelCase like the rest of the API.
 */

/** value -> weight, summing to 1 across a distribution. */
export type Distribution = Record<string, number>;

export interface RegistryField {
  name: string;
  values: string[];
  dtype: 'categorical' | 'numeric';
  description?: string | null;
}

/** A prior with no conditions: one sampler, used for every building. */
export interface UnconditionalPriorSpec {
  sampler: Record<string, unknown>;
}

/** A clipped normal, the sampler a numeric prior uses. */
export interface NormalSampler {
  mean: number;
  std: number;
  clip_min: number | null;
  clip_max: number | null;
}

/**
 * A prior that dispatches on another feature's value.
 *
 * This is how a *numeric* field gets conditioned: `joints` compiles to categorical
 * samplers only, so a per-combination normal is authored here instead, alongside a
 * compound-key entry in the same `priors` map that the sampler runs first.
 */
export interface ConditionalPriorSpec {
  source_feature: string;
  conditions: Array<{ match_val: string; sampler: Record<string, unknown> }>;
  fallback_prior: Record<string, unknown> | null;
}

export type PriorSpec = UnconditionalPriorSpec | ConditionalPriorSpec;

export function isConditionalPrior(prior: PriorSpec | null | undefined): prior is ConditionalPriorSpec {
  return Boolean(prior && 'source_feature' in prior);
}

export function asNormal(sampler: Record<string, unknown> | null | undefined): NormalSampler {
  return {
    mean: Number(sampler?.mean ?? 0),
    std: Number(sampler?.std ?? 1),
    clip_min: sampler?.clip_min === null || sampler?.clip_min === undefined ? null : Number(sampler.clip_min),
    clip_max: sampler?.clip_max === null || sampler?.clip_max === undefined ? null : Number(sampler.clip_max),
  };
}

/** A prior conditioned on the combination of `condition_on`, keyed by the joined values. */
export interface JointSpec {
  target: string;
  condition_on: string[];
  table: Record<string, Distribution>;
  fallback?: Distribution | null;
  separator?: string;
}

/** Set a feature to a constant for every building. */
export interface FixedOverride {
  set: string | number | boolean;
}

/**
 * Set a feature one way where a test passes and another way where it doesn't.
 *
 * `then`/`otherwise` are literals, `$keep` (leave the building's current value),
 * or `$OtherField` (copy another feature's value).
 */
export interface ConditionalOverride {
  based_on: string;
  equals: string | number;
  then: string | number;
  otherwise: string | number;
}

export type ScenarioOverride = FixedOverride | ConditionalOverride;

export function isConditionalOverride(
  override: ScenarioOverride | undefined
): override is ConditionalOverride {
  return Boolean(override && 'based_on' in override);
}

/** `$keep` in a branch means "leave this building's current value alone". */
export const KEEP_TOKEN = '$keep';

export interface ScenarioSpec {
  name: string;
  overrides: Record<string, ScenarioOverride>;
  /** Column the applied frame is tagged with, so stacked results stay separable. */
  label_column?: string | null;
  /** Whether the overridden features are themselves resampled (usually not). */
  resample_changed_features?: boolean;
}

export interface PriorConfig {
  registry: { fields: RegistryField[] };
  priors: Record<string, PriorSpec>;
  joints: JointSpec[];
  scenarios: ScenarioSpec[];
}

/** A feature a scenario can override, or (context only) merely branch on. */
export interface ScenarioTarget {
  name: string;
  dtype: 'categorical' | 'numeric';
  values: string[];
  dependsOn: string[];
  /** True for a field read from the GIS data: testable, but not overridable. */
  contextOnly?: boolean;
}

export interface ScenarioFeatureComparison {
  feature: string;
  dtype: 'categorical' | 'numeric';
  values: string[];
  shares: Array<{ value: string; baseline: number; scenario: number }>;
  numeric: {
    baselineMean: number;
    scenarioMean: number;
    baselineStd: number;
    scenarioStd: number;
  } | null;
}

export interface ScenarioComparison {
  name: string;
  /** Features the scenario overrides directly. */
  changed: string[];
  /** Features resampled because they depend on a changed one. */
  downstream: string[];
  resampleChangedFeatures: boolean;
  labelColumn: string | null;
  features: ScenarioFeatureComparison[];
}

export interface ScenarioPreview {
  n: number;
  seed: number | null;
  contextFields: string[];
  contextRowCount: number;
  contextSource: 'gis' | 'synthetic';
  scenarios: ScenarioComparison[];
}

/** Where a conditioning field's values come from. */
export type CandidateSource = 'semantic' | 'gis' | 'sampled';

export interface ConditioningCandidate {
  name: string;
  source: CandidateSource;
  dtype: 'categorical' | 'numeric';
  /** The field's declared domain (semantic field options, or observed values for a GIS column). */
  declaredValues: string[];
  /** What actually appears in the GIS rows, most common first. */
  observedValues: string[];
  counts: Record<string, number>;
  rowCount: number;
  presentCount: number;
  coverage: number;
  cardinality: number;
  description?: string | null;
  sourceColumn?: string | null;
  /** False for raw numeric columns: they must be bucketed into a semantic field first. */
  conditionable: boolean;
  highCardinality: boolean;
  numericSummary: { mean: number; std: number; min: number; max: number } | null;
}

export interface ConditioningFieldsResponse {
  candidates: ConditioningCandidate[];
  rowCount: number;
  hasGisData: boolean;
  gisValidated: boolean;
}

export interface ConditionPreview {
  compoundKey: string | null;
  keys: Array<{ key: string; count: number }>;
  keyCount: number;
  coveredRows: number;
  rowCount: number;
  coverage: number;
}

/** How a generated prior's weights were arrived at. */
export type GenerationMethod = 'uniform' | 'empirical';

export interface GeneratedKey {
  key: string;
  conditionValues?: string[];
  count: number;
  supportingCount?: number;
  /** True when this row's weights were counted from data rather than inherited. */
  estimated: boolean;
  weights: Distribution;
  /** Set for a numeric target: the normal fitted to this combination. */
  numeric?: NormalSampler;
}

export interface GeneratedPrior {
  target: string;
  /** `conditional` is a numeric target conditioned on a combination. */
  mode: 'unconditional' | 'joint' | 'conditional';
  prior: UnconditionalPriorSpec | null;
  /** Entries to merge into `config.priors`; for a conditional prior this also carries its compound key. */
  priors: Record<string, PriorSpec>;
  joint: JointSpec | null;
  keys: GeneratedKey[];
  fallback: Distribution | null;
  fallbackNumeric?: NormalSampler;
  compoundKey?: string;
  warnings: string[];
}

export interface DependencyNode {
  name: string;
  /** `context` comes from GIS; `compound` is a generated join key; the rest are sampled. */
  kind: 'context' | 'compound' | 'conditional' | 'unconditional';
  dependsOn: string[];
  depth: number;
}

export interface DependencyGraph {
  nodes: DependencyNode[];
  edges: Array<{ from: string; to: string }>;
}

export interface PriorValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  registryFields: string[];
  priorTargets: string[];
  sampledFeatures: string[];
  contextFields?: string[];
  scenarios?: string[];
  dependencies: DependencyGraph;
}

export interface SampleBreakdown {
  field: string;
  values: string[];
  rows: Array<{ key: string; count: number; shares: number[] }>;
}

export interface SampleDistribution {
  feature: string;
  kind: 'conditional' | 'unconditional';
  dtype: 'categorical' | 'numeric';
  dependsOn: string[];
  marginal: Array<{ value: string; share: number }>;
  histogram: {
    bins: Array<{ start: number; end: number; count: number }>;
    mean: number;
    std: number;
    min: number;
    max: number;
  } | null;
  breakdown: SampleBreakdown | null;
  /** Per-combination statistics for a conditioned numeric feature. */
  numericBreakdown: {
    field: string;
    rows: Array<{ key: string; count: number; mean: number; std: number; min: number; max: number }>;
  } | null;
}

export interface SampleSummary {
  n: number;
  seed: number | null;
  contextFields: string[];
  contextRowCount: number;
  /** `gis` when the draws ran over real buildings, `synthetic` when no context was needed. */
  contextSource: 'gis' | 'synthetic';
  distributions: SampleDistribution[];
  sampleRows: Record<string, string | number>[];
}

export interface PriorTreesState {
  config: PriorConfig;
  selectedTemplate: string | null;
  /** The prior currently open in the editor. */
  selectedTarget: string | null;
  valid: boolean;
  validationErrors: string[];
  validationWarnings: string[];
  dependencies: DependencyGraph;
  sample: SampleSummary | null;
  scenarioPreview: ScenarioPreview | null;
}

export interface PriorTreeTemplateSummary {
  name: string;
  filename: string;
  description?: string;
}
