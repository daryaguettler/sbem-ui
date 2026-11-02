// "What decides each part?": record names follow the characteristics list, not the click order.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setPartForField, getSelectorAtPath, buildSelectorCombinations } from '../src/lib/utils/componentMapTree.ts';
import { defaultSuffix } from '../src/lib/utils/modelParts.ts';

const nodes = {
  'Operations.SpaceUse.Lighting': { componentType: 'Lighting' },
  'Operations.SpaceUse.Occupancy.Schedule': { componentType: 'Year' },
  'Operations.SpaceUse.Lighting.Schedule': { componentType: 'Year' },
};
const order = ['Typology', 'Age', 'Income'];
const fields = [{ name: 'Typology', options: ['Residential', 'NonResidential'] }, { name: 'Age', options: ['Pre_1980', 'Post_1980'] }, { name: 'Income', options: ['Low', 'High'] }];

test('Lighting depends on Typology and Age, whatever the click order', () => {
  const L = 'Operations.SpaceUse.Lighting';
  let map: Record<string, unknown> = {};
  map = setPartForField(map, L, 'Age', true, order, defaultSuffix(L, nodes));
  map = setPartForField(map, L, 'Typology', true, order, defaultSuffix(L, nodes));
  const sel = getSelectorAtPath(map, L)!;
  assert.deepEqual(sel.source_fields, ['Typology', 'Age']);
  assert.equal(sel.suffix, undefined);
  assert.deepEqual(buildSelectorCombinations(sel.source_fields, fields, sel.suffix).map((c) => c.name).sort(),
    ['NonResidential_Post_1980', 'NonResidential_Pre_1980', 'Residential_Post_1980', 'Residential_Pre_1980']);
  map = setPartForField(map, L, 'Age', false, order);
  assert.deepEqual(getSelectorAtPath(map, L)!.source_fields, ['Typology']);
});

test('Occupancy schedule depends on Typology and Income, with its own suffix', () => {
  const P = 'Operations.SpaceUse.Occupancy.Schedule';
  let map: Record<string, unknown> = {};
  map = setPartForField(map, P, 'Income', true, order, defaultSuffix(P, nodes));
  map = setPartForField(map, P, 'Typology', true, order, defaultSuffix(P, nodes));
  const sel = getSelectorAtPath(map, P)!;
  assert.deepEqual(sel.source_fields, ['Typology', 'Income']);
  assert.equal(sel.suffix, 'OccupancySchedule');
});
