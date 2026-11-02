/**
 * Tutorial mode: a guided walk from a new project to globi's run files. Each step points
 * at one control on one page (its `data-tour` target) and ticks itself off from state the
 * app already keeps, so starting the tutorial on a half-built project lands on the next
 * step still to do.
 */

import { derived, get, writable } from 'svelte/store';
import type { WorkflowId } from '../types/workflow';
import { characteristics } from './characteristics';
import { dirtyKinds, savedAt } from './projectArtifacts';
import { partRulesStore } from './partRulesStore';
import { gisDataset, navigateTo, readinessChecks } from './projectStore';
import { workspaceStore } from './workspaceStore';

function persisted<T>(key: string, fallback: T) {
  let initial = fallback;
  try {
    const saved = localStorage.getItem(key);
    if (saved !== null) initial = JSON.parse(saved);
  } catch {
    // storage blocked or unreadable: start from the default
  }
  const store = writable<T>(initial);
  store.subscribe((value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // not persisted, but still applied for this session
    }
  });
  return store;
}

export const tutorialOn = persisted('sbem-ui:tutorial', false);
export const tutorialStep = persisted('sbem-ui:tutorial-step', 0);

/** Outcomes no other store keeps: set by the page that produces them, reset per project. */
export const tutorialMarks = writable({ sampling: false, runFiles: false });

interface Snapshot {
  open: boolean;
  gis: { validated: boolean } | null;
  howKnown: string[];
  ready: Record<string, boolean>;
  /** Each readiness check's message: what is still missing when it isn't ready. */
  detail: Record<string, string>;
  saved: Record<string, string | null>;
  dirty: number;
  varies: boolean;
  marks: { sampling: boolean; runFiles: boolean };
}

export interface TutorialStep {
  id: string;
  /** null: the project picker, before any project is open. */
  workflow: WorkflowId | null;
  title: string;
  body: string;
  /** The `data-tour` attributes of the boxes and controls to outline; whichever are on screen. */
  targets: string[];
  /** Omitted for steps the app can't observe (reading, choosing): those just have Next. */
  done?: (s: Snapshot) => boolean;
  /** While not done: what is still missing, when the step's button alone isn't enough. */
  why?: (s: Snapshot) => string;
}

const unsaved = (s: Snapshot) => (s.dirty ? `${s.dirty} file${s.dirty === 1 ? '' : 's'} still unsaved: press Save.` : '');

export const TUTORIAL_STEPS: TutorialStep[] = [
  {
    id: 'template',
    workflow: null,
    title: 'Name the project and pick a template',
    body: 'Give the project a name and choose a component library. The template brings the library and a weather file, so the model runs before you decide anything.',
    targets: ['picker-name', 'template'],
  },
  {
    id: 'create',
    workflow: null,
    title: 'Choose a folder and create it',
    body: 'Type the folder the project lives in. To run the commands the app prints later, put it inside the globi folder, under inputs/. Then press Create project.',
    targets: ['picker-path'],
    done: (s) => s.open,
  },
  {
    id: 'gis-load',
    workflow: 'gis-cleaning',
    title: 'Load your buildings',
    body: 'Upload a CSV or GeoJSON with one row per building, or press Use sample buildings to follow along with example data.',
    targets: ['gis-upload'],
    done: (s) => s.gis !== null,
  },
  {
    id: 'gis-match',
    workflow: 'gis-cleaning',
    title: 'Check the matched columns',
    body: 'Each model input needs the column that holds it. The app guesses from the column names, so check its picks. Required inputs (ID, floors, height) must be matched.',
    targets: ['gis-match'],
  },
  {
    id: 'gis-missing',
    workflow: 'gis-cleaning',
    title: 'Decide which gaps matter',
    body: 'Tick the columns later steps depend on: a building missing a value there can’t be classified. Leave optional columns unticked so their gaps don’t drop buildings.',
    targets: ['gis-missing'],
  },
  {
    id: 'gis-validate',
    workflow: 'gis-cleaning',
    title: 'Validate',
    body: 'Press Validate. It saves the cleaned buildings that every later step reads, and ticks GIS Cleaning in the sidebar.',
    targets: ['gis-validate'],
    done: (s) => Boolean(s.gis?.validated),
    why: (s) => (s.gis ? 'Not validated yet. If you pressed Validate, read the problems listed under it, fix the matches or untick those columns, and validate again.' : 'Load buildings first.'),
  },
  {
    id: 'char-data',
    workflow: 'characteristics',
    title: 'Add a characteristic from your data',
    body: 'Under “What does your data already tell you?”, click a column that sets buildings apart, such as building use or year built. (Already have some? Press Add first.)',
    targets: ['char-from-data', 'char-add'],
    done: (s) => s.howKnown.includes('data'),
  },
  {
    id: 'char-values',
    workflow: 'characteristics',
    title: 'Check its values',
    body: 'Keep the values few and mutually exclusive, so every building gets exactly one. Add a value now if a retrofit will need one no building has yet, such as a heat pump.',
    targets: ['char-values'],
  },
  {
    id: 'char-known',
    workflow: 'characteristics',
    title: 'Check every building gets a value',
    body: 'This says how each building gets its value: from a column, grouped into your values. Make sure every column entry is grouped, so no building is left without one.',
    targets: ['char-known'],
  },
  {
    id: 'char-estimate',
    workflow: 'characteristics',
    title: 'Optional: add one you estimate',
    body: 'For something your data doesn’t record, such as heating system, press Add and pick one under “What do you need to estimate?”, then set the odds of each value. Skip this if your data has everything.',
    targets: ['char-estimate', 'char-add'],
    done: (s) => s.howKnown.includes('estimate') && s.ready.estimates,
    why: (s) => (s.howKnown.includes('estimate') ? s.detail.estimates : ''),
  },
  {
    id: 'char-save',
    workflow: 'characteristics',
    title: 'Save the characteristics',
    body: 'Press Save. Each characteristic still shows “1 to fix” (not used yet) until a model part varies by it in the next step; that is expected.',
    targets: ['char-save'],
    done: (s) => Boolean(s.saved['semantic-fields']) && s.dirty === 0,
    why: unsaved,
  },
  {
    id: 'map-open',
    workflow: 'model-parts',
    title: 'Open a model part',
    body: 'Every card is a part of the energy model. A dashed square means it is still on the template’s default. Click a part that should differ between your buildings, such as Walls.',
    targets: ['map-cards'],
  },
  {
    id: 'map-varies',
    workflow: 'model-parts',
    title: 'Make it vary',
    body: 'Choose Varies by… and click the characteristic it depends on. You get one row per value.',
    targets: ['part-mode'],
    done: (s) => s.varies,
    why: () => 'After Varies by…, click one of the characteristic chips.',
  },
  {
    id: 'map-rows',
    workflow: 'model-parts',
    title: 'Pick a component for each value',
    body: 'Click each row’s component and pick one from the library, or build one (By U-value, Build layers). Rows with the same colour share one component, so you only build what differs.',
    targets: ['part-rows'],
  },
  {
    id: 'map-save',
    workflow: 'model-parts',
    title: 'Save',
    body: 'Press Save. It writes the component map, then checks every building against the library.',
    targets: ['map-save'],
    done: (s) => Boolean(s.saved['part-rules'] ?? s.saved['component-map']) && s.dirty === 0,
    why: unsaved,
  },
  {
    id: 'map-runs',
    workflow: 'model-parts',
    title: 'Check every building runs',
    body: 'The badge should read ✓ buildings run. If it says doesn’t run, click it to see which part has no component for which values, pick one for those rows, and Save again.',
    targets: ['map-status', 'map-check'],
    done: (s) => s.ready['model-parts'],
    why: (s) => s.detail['model-parts'],
  },
  {
    id: 'retro-add',
    workflow: 'retrofits',
    title: 'Add a retrofit package',
    body: 'A package is a change you want to test, compared against the baseline. Press Add package and give it a name.',
    targets: ['retro-add'],
  },
  {
    id: 'retro-measure',
    workflow: 'retrofits',
    title: 'Add a measure',
    body: 'Press Add measure, choose the characteristic to change and the value it becomes, e.g. heating → heat pump. “if” limits it to some buildings. Press Add.',
    targets: ['retro-measure'],
  },
  {
    id: 'retro-save',
    workflow: 'retrofits',
    title: 'Save the package',
    body: 'Press Save. Each package becomes a scenario in the run files.',
    targets: ['retro-save'],
    done: (s) => Boolean(s.saved.retrofits),
  },
  {
    id: 'sampling-buildings',
    workflow: 'sampling',
    title: 'Choose which buildings to simulate',
    body: 'All buildings, a random subset, or a few per combination of characteristics (stratified).',
    targets: ['sampling-buildings'],
  },
  {
    id: 'sampling-draws',
    workflow: 'sampling',
    title: 'Choose the draws',
    body: 'With estimated characteristics, each building is simulated several times with different draws, which shows the spread. Without any, one draw is enough.',
    targets: ['sampling-draws'],
  },
  {
    id: 'sampling-write',
    workflow: 'sampling',
    title: 'Write the sampled buildings',
    body: 'Press Write sampled buildings. It writes the buildings file globi’s batch run reads.',
    targets: ['sampling-write'],
    done: (s) => s.marks.sampling,
  },
  {
    id: 'exec-ready',
    workflow: 'model-execution',
    title: 'Check readiness',
    body: 'Every line should say Ready. Go to step jumps to whatever is left.',
    targets: ['exec-readiness'],
    done: (s) => Object.values(s.ready).every(Boolean),
    why: (s) => Object.entries(s.ready).filter(([, ready]) => !ready).map(([id]) => s.detail[id]).join(' '),
  },
  {
    id: 'exec-building',
    workflow: 'model-execution',
    title: 'Describe one building to run',
    body: 'Pick a value for each characteristic, including the scenario (Baseline or a package), and the building’s size. The weather file comes from the template.',
    targets: ['exec-building'],
  },
  {
    id: 'exec-generate',
    workflow: 'model-execution',
    title: 'Generate the globi files',
    body: 'Press Generate globi files. It writes building.yml, plus the batch files when buildings were sampled.',
    targets: ['globi-generate'],
    done: (s) => s.marks.runFiles,
  },
  {
    id: 'exec-run',
    workflow: 'model-execution',
    title: 'Run it',
    body: 'In a terminal, go to the folder named after “Run from”, then paste the first command. In about 10 seconds it prints the end uses. To compare a package, change the scenario, generate again and rerun.',
    targets: ['exec-commands'],
  },
];

/** The app state the steps read. */
export const tutorialSnapshot = derived(
  [workspaceStore, gisDataset, characteristics, readinessChecks, savedAt, dirtyKinds, partRulesStore, tutorialMarks],
  ([$workspace, $gis, $characteristics, $checks, $saved, $dirty, $rules, $marks]): Snapshot => ({
    open: $workspace.open,
    gis: $gis,
    howKnown: $characteristics.map((view) => view.howKnown),
    ready: Object.fromEntries($checks.map((check) => [check.id, check.ready])),
    detail: Object.fromEntries($checks.map((check) => [check.id, check.detail])),
    saved: $saved,
    dirty: $dirty.length,
    varies: Object.values($rules.rules?.parts ?? {}).some((rule) => rule.depends_on.length > 0),
    marks: $marks,
  })
);

/** Whether each step is done, in step order. A step the app can't observe counts as done
 * once a later observable step is, so starting mid-way lands after it. */
export const tutorialDone = derived(tutorialSnapshot, (snapshot) => {
  const done = TUTORIAL_STEPS.map((step) => step.done?.(snapshot) ?? false);
  for (let i = done.length - 2; i >= 0; i--) {
    if (!TUTORIAL_STEPS[i].done) done[i] = done[i + 1];
  }
  return done;
});

export function goToStep(index: number) {
  const clamped = Math.min(Math.max(index, 0), TUTORIAL_STEPS.length - 1);
  tutorialStep.set(clamped);
  const workflow = TUTORIAL_STEPS[clamped].workflow;
  if (workflow && get(workspaceStore).open) navigateTo(workflow);
}

/** Turn the tutorial on at the first step still to do. */
export function startTutorial() {
  tutorialOn.set(true);
  const next = get(tutorialDone).indexOf(false);
  goToStep(next === -1 ? TUTORIAL_STEPS.length - 1 : next);
}
