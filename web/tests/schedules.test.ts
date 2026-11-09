// Schedule editor helpers: parametric profiles, pasting, clamping, renames that keep references.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  clampToLimit,
  defaultDraft,
  parametric,
  parsePasted,
  removeProfile,
  renameProfile,
  renameWeek,
  snap,
} from '../src/lib/utils/schedules.ts';

test('parametric: a peak period with ramps, and one that wraps past midnight', () => {
  const day = parametric({ on: 8, off: 18, base: 0.1, peak: 1, ramp: 1 });
  assert.equal(day.length, 24);
  assert.deepEqual([day[7], day[8], day[9], day[17], day[18]], [0.1, 0.55, 1, 0.55, 0.1]);

  const night = parametric({ on: 22, off: 6, base: 0, peak: 1, ramp: 0 });
  assert.deepEqual([night[21], night[22], night[0], night[5], night[6]], [0, 1, 1, 1, 0]);
  assert.ok(parametric({ on: 0, off: 0, base: 0, peak: 0.7, ramp: 2 }).every((v) => v === 0.7));
});

test('parsePasted takes a spreadsheet column or a comma row, and refuses the wrong count', () => {
  const column = Array.from({ length: 24 }, (_, h) => String(h / 24)).join('\n');
  assert.equal((parsePasted(column) as number[])[12], 0.5);
  assert.equal((parsePasted(`${'1,'.repeat(23)}1`) as number[]).length, 24);
  assert.match(parsePasted('1\t2\t3') as string, /got 3/);
  assert.match(parsePasted(`${'1 '.repeat(23)}x`) as string, /"x" is not a number/);
});

test('clamping and snapping keep values inside the limit', () => {
  assert.deepEqual(clampToLimit([-1, 0.5, 3], 'Fraction'), [0, 0.5, 1]);
  assert.equal(snap(0.312, 'Fraction'), 0.3);
  assert.equal(snap(21.3, 'Temperature'), 21.5);
});

test('renaming a profile or week updates what points to it; a used profile cannot be removed', () => {
  let draft = defaultDraft('Office');
  draft = renameProfile(draft, 'Weekday', 'Workday')!;
  assert.equal(draft.weeks['All year'].Monday, 'Workday');
  assert.ok('Workday' in draft.profiles && !('Weekday' in draft.profiles));
  assert.equal(renameProfile(draft, 'Workday', 'Weekend'), null);
  assert.equal(renameProfile(draft, 'Workday', 'a__b'), null);

  draft = renameWeek(draft, 'All year', 'Winter')!;
  assert.equal(draft.months.July, 'Winter');
  assert.equal(removeProfile(draft, 'Workday'), null);
});
