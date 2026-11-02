/**
 * One building characteristic seen across the three GloBI files it lives in:
 * its values and GIS rule (semantic-fields.yaml), its estimate (priors.yaml), and
 * the model parts it chooses (component-map.yaml). Pure functions over the existing
 * store states, so the characteristics page never holds a copy of its own.
 */

import type { SemanticField } from '../types/semanticFields';
import { isConditionalPrior, type PriorConfig, type ScenarioOverride } from '../types/priorTrees';
import { COMPOUND_PREFIX, jointFor, priorTargets } from '../stores/priorTreesStore';
import { collectSelectors, fieldStatusAtPath } from './componentMapTree';

export type HowKnown = 'data' | 'estimate';

export interface CharacteristicPart {
  path: string;
  status: 'own' | 'inherited';
  /** For an inherited part, the ancestor whose selector reaches it. */
  from?: string;
}

export interface CharacteristicView {
  field: SemanticField;
  howKnown: HowKnown;
  issues: string[];
  hasEstimate: boolean;
  dependsOn: string[];
  parts: CharacteristicPart[];
  /** Library records needed by the selectors this characteristic is part of. */
  recordCount: number;
}

export function howKnown(field: SemanticField): HowKnown {
  return field.type === 'stochastic' ? 'estimate' : 'data';
}

/** Problems with a field's values and GIS rule that don't need the data to spot. */
export function ruleIssues(field: SemanticField): string[] {
  const issues: string[] = [];
  if (!field.name.trim()) issues.push('Give it a name.');
  if (field.options.length === 0) issues.push('Add at least one value.');
  const seen = new Set<string>();
  for (const option of field.options) {
    if (seen.has(option)) issues.push(`"${option}" is listed twice.`);
    seen.add(option);
  }
  if (howKnown(field) !== 'data') return issues;

  const rule = field.transformationRule;
  if (!rule?.sourceColumn) {
    issues.push('Choose the GIS column it comes from.');
    return issues;
  }
  const options = new Set(field.options);

  if (rule.type === 'numeric_range') {
    const ranges = rule.numericRanges ?? [];
    if (ranges.length === 0) issues.push('Add a range for each value.');
    for (const range of ranges) {
      if (!options.has(range.label)) issues.push(`Range "${range.label}" is not one of the values.`);
      if (range.min > range.max) issues.push(`Range "${range.label}" starts above where it ends.`);
    }
    // Bounds are inclusive on both ends (as the server applies them), so touching counts.
    const sorted = [...ranges].sort((a, b) => a.min - b.min);
    let widest = sorted[0];
    for (const range of sorted.slice(1)) {
      if (range.min <= widest.max) issues.push(`Ranges "${widest.label}" and "${range.label}" overlap.`);
      if (range.max > widest.max) widest = range;
    }
  }

  if (rule.type === 'categorical_mapping') {
    const groups = rule.categoricalGroups ?? [];
    if (groups.length === 0) issues.push("Map the column's values to these values.");
    for (const group of groups) {
      if (!options.has(group.groupLabel)) issues.push(`"${group.groupLabel}" is not one of the values.`);
    }
  }
  return issues;
}

/** What a target's estimate is conditioned on, in either of the two shapes a prior can take. */
export function dependsOn(config: PriorConfig, target: string): string[] {
  const joint = jointFor(config, target);
  if (joint) return [...joint.condition_on];
  const prior = config.priors[target];
  if (!isConditionalPrior(prior)) return [];
  const key = config.priors[prior.source_feature];
  const fields =
    key && !isConditionalPrior(key) ? (key.sampler.features_to_concatenate as string[] | undefined) : undefined;
  return fields ? [...fields] : [prior.source_feature];
}

/** Estimates that would lose a condition if `name` went away. */
export function dependentsOf(config: PriorConfig, name: string): string[] {
  return priorTargets(config).filter((target) => target !== name && dependsOn(config, target).includes(name));
}

/** Values an estimate gives weight to, for categorical estimates. */
function estimateValues(config: PriorConfig, target: string): string[] {
  const joint = jointFor(config, target);
  if (joint) {
    const rows = [...Object.values(joint.table), ...(joint.fallback ? [joint.fallback] : [])];
    return [...new Set(rows.flatMap((row) => Object.keys(row)))];
  }
  const prior = config.priors[target];
  if (!prior || isConditionalPrior(prior)) return [];
  return (prior.sampler.values as string[] | undefined) ?? [];
}

export function estimateIssues(field: SemanticField, config: PriorConfig): string[] {
  if (howKnown(field) !== 'estimate') return [];
  if (!priorTargets(config).includes(field.name)) return ['No estimate yet.'];
  const options = new Set(field.options);
  return estimateValues(config, field.name)
    .filter((value) => !options.has(value))
    .map((value) => `The estimate mentions "${value}", which is no longer one of the values.`);
}

/**
 * Data-backed characteristics first, in list order, then estimates so that each one
 * comes after the characteristics it depends on. Dependencies outside the list (raw
 * GIS columns) are already known; a cycle falls back to list order.
 */
export function characteristicOrder(fields: SemanticField[], config: PriorConfig): SemanticField[] {
  const ordered = fields.filter((field) => howKnown(field) === 'data');
  let pending = fields.filter((field) => howKnown(field) === 'estimate');
  while (pending.length > 0) {
    const waiting = new Set(pending.map((field) => field.name));
    const ready = pending.find((field) =>
      dependsOn(config, field.name).every((name) => name === field.name || !waiting.has(name))
    );
    const next = ready ?? pending[0];
    ordered.push(next);
    pending = pending.filter((field) => field !== next);
  }
  return ordered;
}

function optionCount(fields: SemanticField[], name: string): number {
  return fields.find((field) => field.name === name)?.options.length || 1;
}

/** Library records every selector needs, and rows every estimate table has. */
export function comboBudget(
  componentMap: Record<string, unknown> | null,
  fields: SemanticField[],
  config: PriorConfig
): { records: number; estimateRows: number } {
  const product = (names: string[]) => names.reduce((total, name) => total * optionCount(fields, name), 1);
  const records = componentMap
    ? collectSelectors(componentMap).reduce((total, selector) => total + product(selector.source_fields), 0)
    : 0;
  const estimateRows = config.joints.reduce((total, joint) => total + product(joint.condition_on), 0);
  return { records, estimateRows };
}

export function characteristicView(
  field: SemanticField,
  componentMap: Record<string, unknown> | null,
  config: PriorConfig,
  allFields: SemanticField[],
  treePaths: string[]
): CharacteristicView {
  const parts: CharacteristicPart[] = [];
  if (componentMap) {
    for (const path of treePaths) {
      const { status, from } = fieldStatusAtPath(componentMap, path, field.name);
      if (status !== 'off') parts.push({ path, status, from });
    }
  }
  const recordCount = componentMap
    ? collectSelectors(componentMap)
        .filter((selector) => selector.source_fields.includes(field.name))
        .reduce(
          (total, selector) =>
            total + selector.source_fields.reduce((n, name) => n * optionCount(allFields, name), 1),
          0
        )
    : 0;
  const unused =
    field.name && parts.length === 0 && dependentsOf(config, field.name).length === 0
      ? ['Not used yet: tick a model part it changes, or make an estimate depend on it.']
      : [];
  return {
    field,
    howKnown: howKnown(field),
    issues: [...ruleIssues(field), ...estimateIssues(field, config), ...unused],
    hasEstimate: priorTargets(config).includes(field.name),
    dependsOn: dependsOn(config, field.name),
    parts,
    recordCount,
  };
}

/**
 * Rename a feature everywhere the prior config refers to it: registry, prior keys,
 * conditions (including the compound join keys built from them), and scenarios.
 * Option values (table keys) are untouched. Returns `config` itself if nothing changed.
 */
export function renameInPriorConfig(config: PriorConfig, from: string, to: string): PriorConfig {
  // shortcut: compound key names are split on ".", so a field name containing "." won't be renamed inside one.
  const rename = (name: string) => {
    if (name === from) return to;
    if (!name.startsWith(COMPOUND_PREFIX)) return name;
    const parts = name.slice(COMPOUND_PREFIX.length).split('.');
    return COMPOUND_PREFIX + parts.map((part) => (part === from ? to : part)).join('.');
  };
  const renameToken = (value: string | number) =>
    typeof value === 'string' && value === `$${from}` ? `$${to}` : value;

  const priors = Object.fromEntries(
    Object.entries(config.priors).map(([name, prior]) => {
      if (isConditionalPrior(prior)) return [rename(name), { ...prior, source_feature: rename(prior.source_feature) }];
      const features = prior.sampler.features_to_concatenate as string[] | undefined;
      return [
        rename(name),
        features ? { ...prior, sampler: { ...prior.sampler, features_to_concatenate: features.map(rename) } } : prior,
      ];
    })
  );
  const renamed: PriorConfig = {
    registry: { fields: config.registry.fields.map((field) => ({ ...field, name: rename(field.name) })) },
    priors,
    joints: config.joints.map((joint) => ({
      ...joint,
      target: rename(joint.target),
      condition_on: joint.condition_on.map(rename),
    })),
    scenarios: config.scenarios.map((scenario) => ({
      ...scenario,
      overrides: Object.fromEntries(
        Object.entries(scenario.overrides).map(([name, override]): [string, ScenarioOverride] => [
          rename(name),
          'based_on' in override
            ? {
                ...override,
                based_on: rename(override.based_on),
                then: renameToken(override.then),
                otherwise: renameToken(override.otherwise),
              }
            : override,
        ])
      ),
    })),
  };
  return JSON.stringify(renamed) === JSON.stringify(config) ? config : renamed;
}
