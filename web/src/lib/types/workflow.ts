export type WorkflowId =
  | 'gis-cleaning'
  | 'semantic-fields'
  | 'component-library'
  | 'component-map'
  | 'prior-trees'
  | 'retrofits'
  | 'sampling'
  | 'model-execution'
  | 'project-files';

export interface GisDatasetSummary {
  filename: string;
  rowCount: number;
  validated: boolean;
  columnCount: number;
}

export interface ReadinessCheck {
  id: string;
  label: string;
  ready: boolean;
  workflow: WorkflowId;
  detail: string;
}
