import type { CategoricalGroup, GISColumn, RangeMapping, SemanticField } from '../types/semanticFields';

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
