import { derived, writable } from 'svelte/store';
import type { GisDatasetSummary, ReadinessCheck, WorkflowId } from '../types/workflow';
import { semanticFieldsStore } from './semanticFieldsStore';
import { componentMapStore } from './componentMapStore';
import { priorTargets, priorTreesStore } from './priorTreesStore';

export const currentWorkflow = writable<WorkflowId>('gis-cleaning');
export const gisDataset = writable<GisDatasetSummary | null>(null);

export function navigateTo(workflow: WorkflowId) {
  currentWorkflow.set(workflow);
}

export const readinessChecks = derived(
  [gisDataset, semanticFieldsStore, componentMapStore, priorTreesStore],
  ([$gis, $semantic, $componentMap, $priors]): ReadinessCheck[] => {
    const stochasticFields = $semantic.fields.filter(
      (field) => field.type === 'stochastic' && field.requiresPrior
    );
    // A field's prior lives in `priors` when unconditioned and in `joints` when not.
    const coveredTargets = new Set(priorTargets($priors.config));
    const priorsReady =
      stochasticFields.length === 0 ||
      stochasticFields.every((field) => coveredTargets.has(field.name));

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
        id: 'semantic-fields',
        label: 'Semantic fields defined',
        ready: $semantic.fields.length > 0,
        workflow: 'semantic-fields',
        detail:
          $semantic.fields.length > 0
            ? `${$semantic.fields.length} fields configured`
            : 'Create or load semantic fields.',
      },
      {
        id: 'component-map',
        label: 'Component map configured',
        ready: $componentMap.valid,
        workflow: 'component-map',
        detail: $componentMap.valid
          ? 'Component map references valid semantic fields.'
          : 'Load and validate a component map.',
      },
      {
        id: 'prior-trees',
        label: 'Prior trees cover stochastic fields',
        ready: priorsReady,
        workflow: 'prior-trees',
        detail: priorsReady
          ? 'Required priors are configured.'
          : 'Add priors for stochastic semantic fields.',
      },
    ];
  }
);

export const allArtifactsReady = derived(readinessChecks, ($checks) =>
  $checks.every((check) => check.ready)
);
