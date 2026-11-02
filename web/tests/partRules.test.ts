// Part rules: splitting rows keeps options, merging picks the common one, reuse needs no copies.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  emptyRule,
  partStatus,
  rowsOf,
  setDefault,
  setOption,
  summary,
  usedOptions,
  withDependency,
  withoutDependency,
} from '../src/lib/utils/partRules.ts';

const options = { Typology: ['Office', 'Hospital', 'School'], Age: ['Old', 'New'] };
const order = ['Typology', 'Age'];

test('Office and Hospital share an option; School has its own', () => {
  let rule = withDependency(emptyRule('LPD 10'), 'Typology', order, options);
  rule = setOption(rule, 'School', 'LPD 12');
  assert.deepEqual(rule.cells, { School: 'LPD 12' });
  assert.deepEqual(rowsOf(rule, options).map((r) => r.option), ['LPD 10', 'LPD 10', 'LPD 12']);
  assert.equal(summary(rule), 'by Typology · School: LPD 12 · everything else: LPD 10');
  assert.equal(partStatus(rule), 'varies');
});

test('a new dependency splits rows and keeps their options, whatever the click order', () => {
  let rule = setOption(withDependency(emptyRule('A'), 'Age', order, options), 'Old', 'B');
  rule = withDependency(rule, 'Typology', order, options);
  assert.deepEqual(rule.depends_on, ['Typology', 'Age']);
  assert.deepEqual(rule.cells, { 'Office|Old': 'B', 'Hospital|Old': 'B', 'School|Old': 'B' });
});

test('dropping a dependency merges rows, the most common option winning', () => {
  let rule = withDependency(withDependency(emptyRule('A'), 'Typology', order, options), 'Age', order, options);
  rule = setOption(setOption(rule, 'Office|Old', 'B'), 'Office|New', 'B');
  rule = setOption(rule, 'School|Old', 'C');
  const { rule: merged, conflicts } = withoutDependency(rule, 'Age', options);
  assert.deepEqual(merged.depends_on, ['Typology']);
  assert.deepEqual(merged.cells, { Office: 'B' });
  assert.equal(conflicts, 1); // School: C vs A, a tie keeps the default
});

test('a new default drops rows that already used it', () => {
  const rule = setOption(withDependency(emptyRule('A'), 'Typology', order, options), 'School', 'B');
  assert.deepEqual(setDefault(rule, 'B').cells, {});
  assert.equal(partStatus(emptyRule('A')), 'assumed');
  assert.equal(partStatus({ ...emptyRule('A'), confirmed: true }), 'same');
  assert.equal(partStatus(emptyRule()), 'todo');
});

test('colours follow the options rows use; an unused default gets none', () => {
  let rule = withDependency(emptyRule('Hospital lights'), 'Typology', order, options);
  for (const [key, option] of [['Office', 'LPD 4.9'], ['Hospital', 'LPD 4.9'], ['School', 'LPD 2.2']]) rule = setOption(rule, key, option);
  assert.deepEqual(usedOptions(rule, options), ['LPD 4.9', 'LPD 2.2']);
  assert.deepEqual(usedOptions(emptyRule('A'), options), ['A']);
});
