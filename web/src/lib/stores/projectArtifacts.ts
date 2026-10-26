/**
 * Bridging the project directory on disk and the editor stores.
 *
 * Saved artifacts are written in the same shape as the bundled templates, so loading one
 * back in is just the existing `loadFromTemplate` path pointed at the project's own file.
 * `restoreProjectArtifacts` runs whenever a project is opened; `resetProjectArtifacts`
 * runs when one is closed, so switching projects never leaves the previous one's fields
 * sitting in the editors.
 */

import { derived, get, writable } from 'svelte/store';
import { fetchSavedArtifact, saveArtifact, type ArtifactKind } from '../api/artifacts';
import { componentMapStore } from './componentMapStore';
import { priorTreesStore } from './priorTreesStore';
import { gisDataset } from './projectStore';
import { semanticFieldsStore } from './semanticFieldsStore';
import type { PriorConfig } from '../types/priorTrees';

/** When each artifact was last written to disk, so editors can show "Saved 3 min ago". */
export const savedAt = writable<Record<ArtifactKind, string | null>>({
  'semantic-fields': null,
  'component-map': null,
  priors: null,
  retrofits: null,
});

/** The three files the characteristics page writes, in the order they are saved. */
export const EDITOR_KINDS = ['semantic-fields', 'component-map', 'priors'] as const;
type EditorKind = (typeof EDITOR_KINDS)[number];

/** Each editor file as it was last saved or loaded, to tell which have unsaved edits. */
const savedSnapshot = writable<Partial<Record<EditorKind, string>>>({});

/** The document each editor saves, from the editors' current state. */
function documentFor(
  kind: EditorKind,
  semantic = get(semanticFieldsStore),
  map = get(componentMapStore).map,
  config = get(priorTreesStore).config
): Record<string, unknown> | null {
  if (kind === 'semantic-fields') return semanticFieldsStore.buildApiPayload(semantic);
  if (kind === 'component-map') return map;
  return config as unknown as Record<string, unknown>;
}

function hasContent(kind: EditorKind, doc: Record<string, unknown> | null): boolean {
  if (!doc) return false;
  if (kind === 'semantic-fields') return (doc.fields as unknown[]).length > 0;
  if (kind === 'component-map') return true;
  const config = doc as unknown as PriorConfig;
  return config.registry.fields.length > 0 || Object.keys(config.priors).length > 0 || config.joints.length > 0;
}

export function markSaved(kind: ArtifactKind, timestamp: string | null) {
  savedAt.update((state) => ({ ...state, [kind]: timestamp ?? new Date().toISOString() }));
  if (kind !== 'retrofits') {
    savedSnapshot.update((state) => ({ ...state, [kind]: JSON.stringify(documentFor(kind)) }));
  }
}

/** Editor files whose current content differs from what is on disk (or was never saved). */
export const dirtyKinds = derived(
  [semanticFieldsStore, componentMapStore, priorTreesStore, savedSnapshot],
  ([$semantic, $map, $priors, $snapshot]) =>
    EDITOR_KINDS.filter((kind) => {
      const doc = documentFor(kind, $semantic, $map.map, $priors.config);
      const saved = $snapshot[kind];
      return saved === undefined ? hasContent(kind, doc) : saved !== JSON.stringify(doc);
    })
);

const FILE_NAMES: Record<EditorKind, string> = {
  'semantic-fields': 'semantic-fields.yaml',
  'component-map': 'component-map.yaml',
  priors: 'priors/priors.yaml',
};

/**
 * Save every editor file with unsaved edits, in EDITOR_KINDS order. Stops at the first
 * failure: files already written stay saved, and the error names the one that failed.
 */
export async function saveDirtyArtifacts(): Promise<EditorKind[]> {
  const saved: EditorKind[] = [];
  for (const kind of get(dirtyKinds)) {
    const doc = documentFor(kind);
    if (!doc) continue;
    try {
      const file = await saveArtifact(kind, doc);
      markSaved(kind, file.modifiedAt);
      saved.push(kind);
    } catch (e) {
      const reason = e instanceof Error ? e.message : 'unknown error';
      throw new Error(`Could not save ${FILE_NAMES[kind]}: ${reason}`);
    }
  }
  return saved;
}

function isEmptyDocument(kind: ArtifactKind, content: Record<string, unknown>): boolean {
  if (kind === 'semantic-fields') {
    return !Array.isArray(content.Fields) || content.Fields.length === 0;
  }
  return Object.keys(content).length === 0;
}

/**
 * Load one saved artifact into its editor store. Returns false when nothing was saved
 * (or only the empty scaffold was), leaving the editor on its template picker.
 */
export async function loadSavedArtifact(kind: ArtifactKind): Promise<boolean> {
  const artifact = await fetchSavedArtifact(kind);
  if (!artifact.exists || !artifact.content || isEmptyDocument(kind, artifact.content)) {
    return false;
  }

  if (kind === 'semantic-fields') {
    semanticFieldsStore.loadFromTemplate(artifact.content);
  } else if (kind === 'component-map') {
    componentMapStore.loadFromTemplate(artifact.content, artifact.path);
  } else if (kind === 'priors') {
    priorTreesStore.loadFromTemplate(artifact.content, artifact.path);
  }

  markSaved(kind, artifact.savedAt);
  return true;
}

/**
 * Read the project's GIS session summary, so pages gated on "GIS validated" don't
 * report it missing until the GIS Cleaning page happens to be opened.
 */
async function restoreGisDataset(): Promise<void> {
  const response = await fetch('/api/gis/columns');
  if (!response.ok) return;
  const data = await response.json();
  semanticFieldsStore.setGISColumns(data.columns || []);
  if (data.dataset?.filename !== undefined) {
    gisDataset.set({
      filename: data.dataset.filename,
      rowCount: data.dataset.rowCount || 0,
      validated: Boolean(data.dataset.validated),
      columnCount: data.dataset.columns?.length ?? (data.columns || []).length,
    });
  }
}

/** Re-validate a restored component map, since validity is not saved with the file. */
async function revalidateComponentMap(): Promise<void> {
  const map = get(componentMapStore).map;
  if (!map) return;
  const response = await fetch('/api/component-map/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      component_map: map,
      semantic_fields: get(semanticFieldsStore).fields.map((field) => ({
        name: field.name,
        options: field.options,
      })),
    }),
  });
  if (!response.ok) return;
  const data = await response.json();
  componentMapStore.setValidation(data.valid, data.errors || [], data.generated_names || []);
}

/** Pull every saved artifact of a freshly-opened project back into the editors. */
export async function restoreProjectArtifacts(): Promise<void> {
  await Promise.all([
    ...EDITOR_KINDS.map(async (kind) => {
      try {
        await loadSavedArtifact(kind);
      } catch {
        // A project with an unreadable artifact still opens -- the editor just starts empty.
      }
    }),
    restoreGisDataset().catch(() => {}),
  ]);
  // Needs both the map and the semantic fields loaded.
  await revalidateComponentMap().catch(() => {});
}

/** Clear every editor, so the next project opens without the previous one's state. */
export function resetProjectArtifacts(): void {
  semanticFieldsStore.reset();
  componentMapStore.reset();
  priorTreesStore.reset();
  gisDataset.set(null);
  savedAt.set({ 'semantic-fields': null, 'component-map': null, priors: null, retrofits: null });
  savedSnapshot.set({});
}
