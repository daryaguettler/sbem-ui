// Component priors: starting curves around a value, typed lists, and editing the document.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { SHAPES, defaultSpec, insulated, keyField, parseList, parsePairs, priorFor, uninsulatedSpec, withPrior } from '../src/lib/utils/componentPriors.ts';

test('every shape starts with all its parameters, centred on the current value', () => {
  for (const shape of SHAPES) {
    const spec = defaultSpec(shape.id, 0.3);
    for (const param of shape.params) assert.ok(spec[param.key] !== undefined, `${shape.id} lacks ${param.key}`);
  }
  assert.deepEqual(defaultSpec('triangular', 0.3), { shape: 'triangular', min: 0.24, mode: 0.3, max: 0.36 });
  // a negative or missing value still gives min below max
  const negative = defaultSpec('uniform', -2);
  assert.ok((negative.min as number) < (negative.max as number));
  assert.deepEqual(defaultSpec('uniform', null), { shape: 'uniform', min: 0.8, max: 1.2 });
});

test('lists and parameters are read from what people type', () => {
  assert.deepEqual(parseList('0.6, 0.9 1.1;x'), [0.6, 0.9, 1.1]);
  assert.deepEqual(parsePairs('a=2, scale = 0.5, bad=, c'), { a: 2, scale: 0.5 });
});

test('a construction is known by its U-value, lighting by its W/m²', () => {
  assert.equal(keyField('ConstructionAssembly'), 'U');
  assert.equal(keyField('Lighting'), 'PowerDensity');
  assert.equal(keyField('Year'), null);
});

test('setting and removing a prior keeps the document tidy', () => {
  const prior = { n: 5, fields: { U: defaultSpec('uniform', 1) } };
  let doc = withPrior({ components: {} }, 'ConstructionAssembly', 'Wall', prior);
  assert.deepEqual(priorFor(doc, 'ConstructionAssembly', 'Wall'), prior);
  assert.equal(priorFor(doc, 'Lighting', 'Wall'), null);
  doc = withPrior(doc, 'ConstructionAssembly', 'Wall', { n: 5, fields: {} });
  assert.deepEqual(doc, { components: {} });
});

test('a wall without insulation starts on a curve it can reach: at or below its U', () => {
  const k = { 'Wood stud': 0.19, 'Spray foam': 0.025 };
  assert.equal(insulated([{ ConstructionMaterial: 'Wood stud' }], k), false);
  assert.equal(insulated([{ ConstructionMaterial: 'Wood stud' }, { ConstructionMaterial: 'Spray foam' }], k), true);
  const spec = uninsulatedSpec(1.1108);
  assert.equal(spec.max, 1.11);
  assert.ok((spec.min as number) < (spec.mode as number) && (spec.mode as number) < (spec.max as number));
});

test('links are added, changed and removed; an emptied link goes', async () => {
  const { withLink } = await import('../src/lib/utils/componentPriors.ts');
  let doc = withLink({ components: {} }, 0, { parts: ['A', 'B'], link: 'together' });
  doc = withLink(doc, 1, { parts: ['C', 'D'], link: 0.5 });
  doc = withLink(doc, 0, { parts: ['A', 'B'], link: 0.3 });
  assert.deepEqual(doc.links, [{ parts: ['A', 'B'], link: 0.3 }, { parts: ['C', 'D'], link: 0.5 }]);
  doc = withLink(doc, 0, null);
  assert.deepEqual(doc.links, [{ parts: ['C', 'D'], link: 0.5 }]);
});
