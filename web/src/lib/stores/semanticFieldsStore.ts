import { writable } from 'svelte/store';
import type { SemanticField, GISColumn, SemanticFieldsState } from '../types/semanticFields';
import { ensureTransformationRule } from '../utils/semanticFieldRules';

const initialState: SemanticFieldsState = {
  fields: [],
  gisColumns: [],
  selectedTemplate: null,
  configName: 'Custom Semantic Fields',
  buildingIdCol: 'building_id',
  numFloorsCol: 'num_floors',
  editorMode: 'browse',
  selectedFieldId: null,
};

const { subscribe, set, update } = writable<SemanticFieldsState>(initialState);

function mapTemplateField(field: Record<string, unknown>, index: number): SemanticField {
    const transformation = field.GIS_Source
      ? {
          id: `transform-${index}`,
          type: (field.Transformation as string) || 'categorical_mapping',
          sourceColumn: String(field.GIS_Source),
          targetField: String(field.Name),
          numericRanges: (field.Ranges as Array<{ min: number; max: number; label: string }> | undefined)?.map(
            (range) => ({
              min: Number(range.min),
              max: Number(range.max),
              label: String(range.label),
            })
          ),
          categoricalGroups: (field.Groups as Array<{ group_label?: string; groupLabel?: string; source_values?: string[]; sourceValues?: string[] }> | undefined)?.map(
            (group) => ({
              groupLabel: String(group.group_label || group.groupLabel || ''),
              sourceValues: (group.source_values || group.sourceValues || []).map(String),
            })
          ),
        }
      : undefined;

  return {
    id: `field-${index}`,
    name: String(field.Name),
    type: field.Type === 'stochastic' ? 'stochastic' : 'deterministic',
    // Prefer the saved type; older documents didn't record one, so fall back to
    // inferring it from the transformation rule.
    dataType:
      (field.Data_Type as SemanticField['dataType'] | undefined) ??
      (field.Transformation === 'numeric_range' ? 'numeric' : 'categorical'),
    options: (field.Options as string[]) || [],
    description: field.Description ? String(field.Description) : undefined,
    transformationRule: transformation as SemanticField['transformationRule'],
    requiresPrior: Boolean(field.Requires_Prior),
  };
}

export const semanticFieldsStore = {
  subscribe,
  set,
  update,
  addField: (field: SemanticField) => {
    update((state) => ({
      ...state,
      fields: [...state.fields, field],
      editorMode: 'edit',
    }));
  },
  updateField: (id: string, updates: Partial<SemanticField>) => {
    update((state) => ({
      ...state,
      fields: state.fields.map((field) => (field.id === id ? { ...field, ...updates } : field)),
    }));
  },
  removeField: (id: string) => {
    update((state) => ({
      ...state,
      fields: state.fields.filter((field) => field.id !== id),
    }));
  },
  setGISColumns: (columns: GISColumn[]) => {
    update((state) => ({
      ...state,
      gisColumns: columns,
    }));
  },
  setSelectedTemplate: (template: string | null) => {
    update((state) => ({
      ...state,
      selectedTemplate: template,
    }));
  },
  setConfigMeta: (updates: Partial<Pick<SemanticFieldsState, 'configName' | 'buildingIdCol' | 'numFloorsCol'>>) => {
    update((state) => ({
      ...state,
      ...updates,
    }));
  },
  loadFromTemplate: (templateData: Record<string, unknown>) => {
    const fields = ((templateData.Fields as Record<string, unknown>[]) || []).map(mapTemplateField);

    update((state) => ({
      ...state,
      fields: fields.map((field) =>
        ensureTransformationRule(field, state.gisColumns, { keepRuleType: true })
      ),
      selectedTemplate: String(templateData.Name || 'Template'),
      configName: String(templateData.Name || 'Template'),
      buildingIdCol: String(templateData.Building_ID_col || state.buildingIdCol),
      numFloorsCol: String(templateData.Num_Floors_col || state.numFloorsCol),
      editorMode: 'edit',
      selectedFieldId: fields[0]?.id || null,
    }));
  },
  startFromScratch: () => {
    update((state) => ({
      ...state,
      fields: [],
      selectedTemplate: null,
      configName: 'Custom Semantic Fields',
      editorMode: 'edit',
    }));
  },
  setSelectedField: (fieldId: string | null) => {
    update((state) => ({
      ...state,
      selectedFieldId: fieldId,
    }));
  },
  buildApiPayload: (state: SemanticFieldsState) => ({
    name: state.configName,
    building_id_col: state.buildingIdCol,
    num_floors_col: state.numFloorsCol,
    fields: state.fields.map((field) => ({
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
    })),
  }),
  toExportPayload: (state: SemanticFieldsState) => ({
    Name: state.configName,
    Fields: state.fields.map((field) => ({
      Name: field.name,
      Options: field.options,
      Description: field.description,
      Data_Type: field.dataType,
      Type: field.type === 'stochastic' ? 'stochastic' : undefined,
      Requires_Prior: field.requiresPrior || undefined,
      GIS_Source: field.transformationRule?.sourceColumn,
      Transformation: field.transformationRule?.type,
      Ranges: field.transformationRule?.numericRanges?.map((range) => ({
        min: range.min,
        max: range.max,
        label: range.label,
      })),
      Groups: field.transformationRule?.categoricalGroups?.map((group) => ({
        group_label: group.groupLabel,
        source_values: group.sourceValues,
      })),
    })),
    Building_ID_col: state.buildingIdCol,
    Num_Floors_col: state.numFloorsCol,
  }),
  reset: () => set(initialState),
};
