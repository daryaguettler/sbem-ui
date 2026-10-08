/**
 * Bridging the project directory on disk and the editor stores.
 *
 * Saved artifacts are written in the same shape as the bundled templates, so loading one
 * back in is just the existing `loadFromTemplate` path pointed at the project's own file.
 * `restoreProjectArtifacts` runs whenever a project is opened; `resetProjectArtifacts`
 * runs when one is closed, so switching projects never leaves the previous one's fields
 * sitting in the editors.
 */

import { writable } from 'svelte/store';
import { fetchSavedArtifact, type ArtifactKind } from '../api/artifacts';
import { componentMapStore } from './componentMapStore';
import { priorTreesStore } from './priorTreesStore';
import { gisDataset } from './projectStore';
import { semanticFieldsStore } from './semanticFieldsStore';

/** When each artifact was last written to disk, so editors can show "Saved 3 min ago". */
export const savedAt = writable<Record<ArtifactKind, string | null>>({
  'semantic-fields': null,
  'component-map': null,
  priors: null,
  retrofits: null,
});

export function markSaved(kind: ArtifactKind, timestamp: string | null) {
  savedAt.update((state) => ({ ...state, [kind]: timestamp ?? new Date().toISOString() }));
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

/** Pull every saved artifact of a freshly-opened project back into the editors. */
export async function restoreProjectArtifacts(): Promise<void> {
  const kinds: ArtifactKind[] = ['semantic-fields', 'component-map', 'priors'];
  await Promise.all(
    kinds.map(async (kind) => {
      try {
        await loadSavedArtifact(kind);
      } catch {
        // A project with an unreadable artifact still opens -- the editor just starts empty.
      }
    })
  );
}

/** Clear every editor, so the next project opens without the previous one's state. */
export function resetProjectArtifacts(): void {
  semanticFieldsStore.reset();
  componentMapStore.reset();
  priorTreesStore.reset();
  gisDataset.set(null);
  savedAt.set({ 'semantic-fields': null, 'component-map': null, priors: null, retrofits: null });
}
