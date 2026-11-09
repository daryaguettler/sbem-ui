// Odds pasted from a spreadsheet: headers, labelled rows, percentages, and what gets skipped.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FALLBACK_KEY, parsePastedOdds, parseShare } from '../src/lib/utils/pasteOdds.ts';

const VALUES = ['Uninsulated', 'R-11', 'R-19'];

test('shares are read as typed', () => {
  assert.equal(parseShare('0.25'), 0.25);
  assert.equal(parseShare(' 25% '), 25);
  assert.equal(parseShare('0,5'), 0.5);
  assert.equal(parseShare('.5'), 0.5);
  assert.equal(parseShare('Uninsulated'), null);
  assert.equal(parseShare(''), null);
});

test('one row of numbers follows the values in order and is rescaled', () => {
  const { rows, warnings } = parsePastedOdds('60%\t30%\t10%', VALUES);
  assert.deepEqual(rows, [{ key: null, weights: { Uninsulated: 0.6, 'R-11': 0.3, 'R-19': 0.1 } }]);
  assert.deepEqual(warnings, []);
});

test('two columns, value and share, give one distribution', () => {
  const { rows } = parsePastedOdds('R-19\t1\nUninsulated\t3\n', VALUES);
  assert.deepEqual(rows[0].weights, { Uninsulated: 0.75, 'R-11': 0, 'R-19': 0.25 });
});

test('a header picks the columns, and labels pick the combinations', () => {
  const keys = ['pre_1975.Gas', 'pre_1975.Oil', 'post_2003.Gas'];
  const text = [
    'Combination\tR-19\tUninsulated\tTriple',
    'pre_1975 · Gas\t1\t3\t9',
    'Post_2003 / gas\t50%\t50%\t0',
    'pre_1975.Coal\t1\t1\t1',
    'Everything else\t0\t1\t0',
  ].join('\n');
  const { rows, warnings } = parsePastedOdds(text, VALUES, keys);
  assert.deepEqual(rows, [
    { key: 'pre_1975.Gas', weights: { Uninsulated: 0.75, 'R-11': 0, 'R-19': 0.25 } },
    { key: 'post_2003.Gas', weights: { Uninsulated: 0.5, 'R-11': 0, 'R-19': 0.5 } },
    { key: FALLBACK_KEY, weights: { Uninsulated: 1, 'R-11': 0, 'R-19': 0 } },
  ]);
  assert.ok(warnings.some((w) => w.includes('Triple')));
  assert.ok(warnings.some((w) => w.includes('No column for R-11')));
  assert.ok(warnings.some((w) => w.includes('pre_1975.Coal')));
});

test('rows that add up to 0, or have no label in a table, are skipped with a reason', () => {
  assert.match(parsePastedOdds('0\t0\t0', VALUES).warnings[0], /adds up to 0/);
  const unlabelled = parsePastedOdds('1\t2\t3', VALUES, ['a.b']);
  assert.deepEqual(unlabelled.rows, []);
  assert.match(unlabelled.warnings[0], /without a combination name/);
});
