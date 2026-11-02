import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { get } from 'svelte/store';
import { savedAt } from '../src/lib/stores/projectArtifacts.ts';
import { gisDataset, libraryCheck } from '../src/lib/stores/projectStore.ts';
import {
  TUTORIAL_STEPS,
  startTutorial,
  tutorialDone,
  tutorialMarks,
  tutorialSnapshot,
  tutorialStep,
} from '../src/lib/stores/tutorial.ts';

const doneIds = () =>
  get(tutorialDone)
    .map((done, i) => (done ? TUTORIAL_STEPS[i].id : null))
    .filter(Boolean);

test('tutorial steps tick off from app state, and start lands on the first step to do', () => {
  assert.deepEqual(doneIds(), []);
  startTutorial();
  assert.equal(get(tutorialStep), 0);

  gisDataset.set({ filename: 'b.geojson', rowCount: 100, columnCount: 5, validated: false });
  assert.deepEqual(doneIds(), ['gis-load']);
  startTutorial();
  assert.equal(get(tutorialStep), 0, 'no project open yet');

  // Validating ticks the two steps before it that the app can't observe.
  gisDataset.set({ filename: 'b.geojson', rowCount: 100, columnCount: 5, validated: true });
  assert.deepEqual(doneIds(), ['gis-load', 'gis-match', 'gis-missing', 'gis-validate']);

  tutorialMarks.set({ sampling: true, runFiles: false });
  assert.ok(doneIds().includes('sampling-buildings') && doneIds().includes('sampling-write'));
  tutorialMarks.set({ sampling: false, runFiles: false });
});

test('Save on Component Map ticks on its own; a failing check stays open and says why', () => {
  const step = (id: string) => TUTORIAL_STEPS.find((s) => s.id === id)!;
  const doneOf = (id: string) => get(tutorialDone)[TUTORIAL_STEPS.indexOf(step(id))];
  savedAt.update((saved) => ({ ...saved, 'part-rules': '2026-11-02T10:00:00Z' }));
  libraryCheck.set({ ok: false, tested: 3, failed: 1, errors: ['Walls: no component for Pre_1980.'], missing: [], unmapped: [], buildings: 100, source: '' });
  assert.equal(doneOf('map-save'), true);
  assert.equal(doneOf('map-runs'), false);
  assert.equal(step('map-runs').why!(get(tutorialSnapshot)), 'Walls: no component for Pre_1980.');
});

test('every tutorial target is on some page', () => {
  const files = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
      entry.isDirectory() ? files(join(dir, entry.name)) : entry.name.endsWith('.svelte') ? [join(dir, entry.name)] : []
    );
  const source = files('src').map((file) => readFileSync(file, 'utf8')).join('\n');
  for (const step of TUTORIAL_STEPS) {
    for (const target of step.targets) assert.ok(source.includes(`data-tour="${target}"`), `${step.id}: no data-tour="${target}"`);
  }
});
