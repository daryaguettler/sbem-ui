import { derived, get, writable } from 'svelte/store';
import type { GisDatasetSummary, ReadinessCheck, WorkflowId } from '../types/workflow';
import { componentMapStore } from './componentMapStore';
import { priorTargets, priorTreesStore } from './priorTreesStore';
import { workspaceStore } from './workspaceStore';
import { characteristics } from './characteristics';

export const currentWorkflow = writable<WorkflowId>('gis-cleaning');
export const gisDataset = writable<GisDatasetSummary | null>(null);

const WORKFLOW_IDS: WorkflowId[] = [
  'gis-cleaning',
  'characteristics',
  'component-library',
  'retrofits',
  'sampling',
  'model-execution',
  'project-files',
];

const lastWorkflowKey = (projectPath: string) => `sbem-ui:last-workflow:${projectPath}`;

export function navigateTo(workflow: WorkflowId) {
  currentWorkflow.set(workflow);
  const projectPath = get(workspaceStore).workspace?.path;
  if (!projectPath) return;
  try {
    localStorage.setItem(lastWorkflowKey(projectPath), workflow);
  } catch {
    // not remembered across reloads; harmless
  }
}

/** Reopen a project on the step the user last had open, or the first step. */
export function restoreLastWorkflow(projectPath: string) {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(lastWorkflowKey(projectPath));
  } catch {
    saved = null;
  }
  if (saved && RETIRED_WORKFLOWS.has(saved)) saved = 'characteristics';
  currentWorkflow.set(WORKFLOW_IDS.includes(saved as WorkflowId) ? (saved as WorkflowId) : 'gis-cleaning');
}

// Old step ids remembered from before Building Characteristics replaced those pages.
const RETIRED_WORKFLOWS = new Set(['semantic-fields', 'component-map', 'prior-trees']);

export const readinessChecks = derived(
  [gisDataset, characteristics, componentMapStore, priorTreesStore],
  ([$gis, $characteristics, $componentMap, $priors]): ReadinessCheck[] => {
    const toFinish = $characteristics.filter((view) => view.issues.length > 0);
    const estimated = $characteristics.filter((view) => view.howKnown === 'estimate');
    // A field's prior lives in `priors` when unconditioned and in `joints` when not.
    const coveredTargets = new Set(priorTargets($priors.config));
    const missingEstimates = estimated.filter((view) => !coveredTargets.has(view.field.name));
    const characteristicsReady = $characteristics.length > 0 && toFinish.length === 0;

    return [
      {
        id: 'gis',
        label: 'GIS data uploaded and validated',
        ready: Boolean($gis?.validated),
        workflow: 'gis-cleaning',
        detail: $gis?.validated
          ? `${$gis.filename} (${$gis.rowCount} rows)`
          : 'Upload and validate GIS data first.',
      },
      {
        id: 'characteristics',
        label: 'Building characteristics complete',
        ready: characteristicsReady,
        workflow: 'characteristics',
        detail: characteristicsReady
          ? `${$characteristics.length} characteristics, nothing left to fix.`
          : $characteristics.length === 0
            ? 'Add the characteristics that set your buildings apart.'
            : `${toFinish.length} characteristic${toFinish.length === 1 ? '' : 's'} still to finish.`,
      },
      {
        id: 'model-parts',
        label: 'Model parts connected and checked',
        ready: $componentMap.valid,
        workflow: 'characteristics',
        detail: $componentMap.valid
          ? 'Every model part refers to a defined characteristic.'
          : 'Connect model parts, then press Check on Building Characteristics.',
      },
      {
        id: 'estimates',
        label: 'Every estimated characteristic has an estimate',
        ready: missingEstimates.length === 0,
        workflow: 'characteristics',
        detail:
          missingEstimates.length === 0
            ? 'Every estimated characteristic has its odds set.'
            : `No estimate yet for ${missingEstimates.map((view) => view.field.name).join(', ')}.`,
      },
    ];
  }
);

export const allArtifactsReady = derived(readinessChecks, ($checks) =>
  $checks.every((check) => check.ready)
);
