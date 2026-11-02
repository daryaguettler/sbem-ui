import type { CategoricalGroup, GISColumn, RangeMapping, SemanticField } from '../types/semanticFields';
import type { ApiSemanticField } from '../api/assist';

export function parseOptionsText(optionsText: string): string[] {
  return optionsText
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

export function createEmptyField(): SemanticField {
  return {
    id: crypto.randomUUID(),
    name: '',
    type: 'deterministic',
    dataType: 'categorical',
    options: [],
    description: '',
    requiresPrior: false,
  };
}

export function defaultRuleType(field: SemanticField): SemanticField['transformationRule'] extends infer T
  ? T extends { type: infer U }
    ? U
    : 'categorical_mapping'
  : 'categorical_mapping' {
  return field.dataType === 'numeric' ? 'numeric_range' : 'categorical_mapping';
}

export function initNumericRanges(options: string[]): RangeMapping[] {
  return options.map((label, index) => ({
    label,
    min: index === 0 ? 0 : 0,
    max: index === options.length - 1 ? 9999 : 0,
  }));
}

/**
 * Re-fit numeric ranges to an edited options list without losing what the user typed:
 * a range keeps its min/max when its label is still an option, and a renamed option
 * (same position, old label gone) keeps the range that was there. Only genuinely new
 * options get blank ranges.
 */
export function syncNumericRanges(existing: RangeMapping[] | undefined, options: string[]): RangeMapping[] {
  const previous = existing ?? [];
  const byLabel = new Map(previous.map((range) => [range.label, range]));
  const fresh = initNumericRanges(options);
  return options.map((label, index) => {
    const kept = byLabel.get(label);
    if (kept) return kept;
    const atIndex = previous[index];
    if (atIndex && !options.includes(atIndex.label)) return { ...atIndex, label };
    return fresh[index];
  });
}

export function initCategoricalGroups(sourceColumn: string, options: string[], gisColumns: GISColumn[]): CategoricalGroup[] {
  const column = gisColumns.find((entry) => entry.name === sourceColumn);
  if (!column) {
    return [];
  }

  return column.uniqueValues.map((value) => ({
    groupLabel: options.includes(value) ? value : options[0] || value,
    sourceValues: [value],
  }));
}

export function ensureTransformationRule(
  field: SemanticField,
  gisColumns: GISColumn[],
  { keepRuleType = false }: { keepRuleType?: boolean } = {}
): SemanticField {
  if (field.type !== 'deterministic') {
    return { ...field, transformationRule: undefined };
  }

  const existing = field.transformationRule;
  // `keepRuleType` is for loading a saved field, whose rule is already correct;
  // the editor leaves it off so that changing dataType switches the rule.
  const ruleType =
    keepRuleType && existing?.type
      ? existing.type
      : field.dataType === 'numeric'
        ? 'numeric_range'
        : 'categorical_mapping';
  const sourceColumn = existing?.sourceColumn || '';
  let numericRanges = existing?.numericRanges;
  let categoricalGroups = existing?.categoricalGroups;

  if (ruleType === 'numeric_range' && (!numericRanges || numericRanges.length === 0) && field.options.length > 0) {
    numericRanges = initNumericRanges(field.options);
  }

  if (
    ruleType === 'categorical_mapping' &&
    sourceColumn &&
    (!categoricalGroups || categoricalGroups.length === 0)
  ) {
    categoricalGroups = initCategoricalGroups(sourceColumn, field.options, gisColumns);
  }

  return {
    ...field,
    transformationRule: {
      id: existing?.id || crypto.randomUUID(),
      type: ruleType,
      sourceColumn,
      targetField: field.name,
      numericRanges,
      categoricalGroups,
    },
  };
}

/** The editor's camelCase field from the API's snake_case one (inverse of buildApiPayload). */
export function fromApiField(field: ApiSemanticField): SemanticField {
  const rule = field.transformation_rule;
  return {
    id: field.id,
    name: field.name,
    type: field.type,
    dataType: field.data_type,
    options: [...field.options],
    description: field.description ?? undefined,
    requiresPrior: Boolean(field.requires_prior),
    transformationRule: rule
      ? {
          id: rule.id,
          type: rule.type,
          sourceColumn: rule.source_column,
          targetField: rule.target_field,
          numericRanges: rule.numeric_ranges ?? undefined,
          categoricalGroups: rule.categorical_groups?.map((group) => ({
            groupLabel: group.group_label,
            sourceValues: group.source_values,
          })),
        }
      : undefined,
  };
}

/** A field with a new options list, its rule re-fitted without losing typed ranges. */
export function withOptions(field: SemanticField, options: string[], gisColumns: GISColumn[]): SemanticField {
  const next = ensureTransformationRule({ ...field, options }, gisColumns);
  if (next.transformationRule?.type !== 'numeric_range') return next;
  return {
    ...next,
    transformationRule: {
      ...next.transformationRule,
      numericRanges: syncNumericRanges(field.transformationRule?.numericRanges, options),
    },
  };
}
