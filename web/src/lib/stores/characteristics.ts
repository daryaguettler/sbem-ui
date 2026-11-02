/**
 * Building characteristics: a read-only view over the semantic fields, component
 * map and prior stores, plus the only actions that have to change more than one of
 * them at once. Everything else edits the underlying store directly.
 */

import { derived, get } from 'svelte/store';
import { componentMapStore } from './componentMapStore';
import { componentTreeStore } from './componentTreeStore';
import { priorTargets, priorTreesStore } from './priorTreesStore';
import { semanticFieldsStore } from './semanticFieldsStore';
import { ensureTransformationRule } from '../utils/semanticFieldRules';
import { removeFieldFromSelector, collectSelectors, renameFieldInMap } from '../utils/componentMapTree';
import {
  characteristicOrder,
  characteristicView,
  renameInPriorConfig,
  type HowKnown,
} from '../utils/characteristics';

export const characteristics = derived(
  [semanticFieldsStore, componentMapStore, priorTreesStore, componentTreeStore],
  ([$fields, $map, $priors, $tree]) => {
    const treePaths = Object.keys($tree.nodesByPath);
    return characteristicOrder($fields.fields, $priors.config).map((field) =>
      characteristicView(field, $map.map, $priors.config, $fields.fields, treePaths)
    );
  }
);

function findField(name: string) {
  return get(semanticFieldsStore).fields.find((field) => field.name === name);
}

/** Rename a characteristic in its field, every selector, and its estimate and conditions. */
export function renameCharacteristic(from: string, to: string): void {
  const field = findField(from);
  if (!field || !to || from === to) return;
  semanticFieldsStore.updateField(field.id, {
    name: to,
    transformationRule: field.transformationRule && { ...field.transformationRule, targetField: to },
  });

  const map = get(componentMapStore).map;
  if (map) {
    const renamed = renameFieldInMap(map, from, to);
    if (renamed !== map) componentMapStore.setMap(renamed);
  }

  const { config, selectedTarget } = get(priorTreesStore);
  const renamedConfig = renameInPriorConfig(config, from, to);
  if (renamedConfig !== config) priorTreesStore.setConfig(renamedConfig);
  if (selectedTarget === from) priorTreesStore.setSelectedTarget(to);
}

/** Remove a characteristic, its selectors and its estimate. Callers warn first about
 * estimates that depend on it (`dependentsOf`); those keep their now-dangling condition. */
export function removeCharacteristic(name: string): void {
  const field = findField(name);
  if (!field) return;
  semanticFieldsStore.removeField(field.id);

  const map = get(componentMapStore).map;
  if (map) {
    const paths = collectSelectors(map)
      .filter((selector) => selector.source_fields.includes(name))
      .map((selector) => selector.path);
    if (paths.length > 0) {
      componentMapStore.setMap(paths.reduce((next, path) => removeFieldFromSelector(next, path, name), map));
    }
  }

  if (priorTargets(get(priorTreesStore).config).includes(name)) priorTreesStore.removeTarget(name);
}

/** Switch between "from my data" and "estimate it". Each drops what the other needed
 * (the GIS rule, or the estimate), so callers confirm first when there is one. */
export function setHowKnown(name: string, mode: HowKnown): void {
  const field = findField(name);
  if (!field) return;
  if (mode === 'estimate') {
    semanticFieldsStore.updateField(field.id, {
      type: 'stochastic',
      requiresPrior: true,
      transformationRule: undefined,
    });
    return;
  }
  const { gisColumns } = get(semanticFieldsStore);
  semanticFieldsStore.updateField(
    field.id,
    ensureTransformationRule({ ...field, type: 'deterministic', requiresPrior: false }, gisColumns)
  );
  if (priorTargets(get(priorTreesStore).config).includes(name)) priorTreesStore.removeTarget(name);
}
