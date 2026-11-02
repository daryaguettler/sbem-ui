import { derived, get, writable } from 'svelte/store';
import type { GisDatasetSummary, ReadinessCheck, WorkflowId } from '../types/workflow';
import { checkLibrary, type LibraryCheck } from '../api/partRules';
import { priorTargets, priorTreesStore } from './priorTreesStore';
import { workspaceStore } from './workspaceStore';
import { characteristics } from './characteristics';

export const currentWorkflow = writable<WorkflowId>('gis-cleaning');
export const gisDataset = writable<GisDatasetSummary | null>(null);
/** The last library check: every combination the buildings have, resolved with globi's composer. */
export const libraryCheck = writable<LibraryCheck | null>(null);

export async function runLibraryCheck(): Promise<LibraryCheck | null> {
  try {
    const result = await checkLibrary();
    libraryCheck.set(result);
    return result;
  } catch (e) {
    const error = e instanceof Error ? e.message : 'The check failed.';
    libraryCheck.set({ ok: false, tested: 0, failed: 0, errors: [error], missing: [], unmapped: [], buildings: 0, source: '' });
    return null;
  }
}

const WORKFLOW_IDS: WorkflowId[] = [
  'model-parts',
  'gis-cleaning',
  'characteristics',
  'component-library',
  'retrofits',
  'sampling',
  'model-execution',
  'single-building',
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
  if (saved && saved in RETIRED_WORKFLOWS) saved = RETIRED_WORKFLOWS[saved];
  currentWorkflow.set(WORKFLOW_IDS.includes(saved as WorkflowId) ? (saved as WorkflowId) : 'gis-cleaning');
}

// Old step ids remembered from before their pages moved: Building Characteristics replaced the
// first three, and schedule variability is part of the Component Library.
const RETIRED_WORKFLOWS: Record<string, WorkflowId> = {
  'semantic-fields': 'characteristics',
  'component-map': 'characteristics',
  'prior-trees': 'characteristics',
  'schedule-variability': 'component-library',
};

export const readinessChecks = derived(
  [gisDataset, characteristics, libraryCheck, priorTreesStore],
  ([$gis, $characteristics, $check, $priors]): ReadinessCheck[] => {
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
        label: 'Every building finds its model parts in the library',
        ready: Boolean($check?.ok),
        workflow: 'model-parts',
        detail: $check?.ok
          ? $check.buildings
            ? `All ${$check.buildings.toLocaleString()} buildings resolve.`
            : 'Every combination of values resolves.'
          : ($check?.errors[0] ?? 'Open Component Map and press Check.'),
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
