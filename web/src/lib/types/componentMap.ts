export interface ComponentSelector {
  source_fields: string[];
  suffix?: string;
}

export interface ComponentSelectorRecord extends ComponentSelector {
  path: string;
}

export type ComponentMapViewMode = 'graph' | 'table';

export interface ComponentMapState {
  map: Record<string, unknown> | null;
  selectedTemplate: string | null;
  selectedPath: string | null;
  viewMode: ComponentMapViewMode;
  expandedPaths: string[];
  valid: boolean;
  validationErrors: string[];
  generatedNames: string[];
}

export interface ComponentMapTemplateSummary {
  name: string;
  filename: string;
  description?: string;
}

export interface SelectorPreview {
  count: number;
  samples: string[];
}
