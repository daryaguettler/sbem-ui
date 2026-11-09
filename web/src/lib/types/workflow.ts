export type WorkflowId =
  | 'model-parts'
  | 'gis-cleaning'
  | 'characteristics'
  | 'component-library'
  | 'retrofits'
  | 'sampling'
  | 'model-execution'
  | 'single-building'
  | 'simulations'
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
