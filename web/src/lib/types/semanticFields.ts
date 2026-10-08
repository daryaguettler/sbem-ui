/** Types for semantic fields and transformations */

export type FieldDataType = 'numeric' | 'categorical' | 'string';

export type FieldType = 'deterministic' | 'stochastic';

export type TransformationType = 'numeric_range' | 'categorical_mapping' | 'compound';

export interface GISColumn {
  name: string;
  dataType: FieldDataType;
  uniqueValues: string[];
  sampleValues: string[];
  nullable: boolean;
  nullCount?: number;
}

export interface RangeMapping {
  min: number;
  max: number;
  label: string;
}

export interface CategoricalGroup {
  groupLabel: string;
  sourceValues: string[];
}

export interface CompoundFieldLogic {
  fields: string[];
  logic: 'and' | 'or';
  separator: string;
}

export interface TransformationRule {
  id: string;
  type: TransformationType;
  sourceColumn: string;
  targetField: string;
  numericRanges?: RangeMapping[];
  categoricalGroups?: CategoricalGroup[];
  compoundLogic?: CompoundFieldLogic;
}

export interface SemanticField {
  id: string;
  name: string;
  type: FieldType;
  dataType: FieldDataType;
  options: string[];
  description?: string;
  transformationRule?: TransformationRule;
  requiresPrior?: boolean;
  priorId?: string;
}

export interface SemanticFieldsState {
  fields: SemanticField[];
  gisColumns: GISColumn[];
  selectedTemplate: string | null;
  configName: string;
  buildingIdCol: string;
  numFloorsCol: string;
  editorMode: 'browse' | 'edit';
  selectedFieldId: string | null;
}

export interface SemanticFieldTemplateSummary {
  name: string;
  filename: string;
  description?: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

export interface FieldPreviewStats {
  mapped_count: number;
  unmapped_count: number;
  total_count: number;
  coverage_percent: number;
}

export interface FieldPreview {
  field_name: string;
  source_column: string;
  rule_type: string;
  samples: Array<{ source_value: unknown; semantic_value: string | null }>;
  stats: FieldPreviewStats;
}

export interface SemanticFieldsPreview {
  field_previews: FieldPreview[];
  sample_rows: Record<string, unknown>[];
}
