import { test } from 'node:test';
import assert from 'node:assert/strict';
import { get } from 'svelte/store';
import {
  fieldStatusAtPath,
  getSelectorAtPath,
  renameFieldInMap,
  setPartForField,
} from '../src/lib/utils/componentMapTree.ts';
import {
  characteristicOrder,
  characteristicView,
  comboBudget,
  dependentsOf,
  renameInPriorConfig,
  ruleIssues,
} from '../src/lib/utils/characteristics.ts';
import { defaultSuffix, otherPaths } from '../src/lib/utils/modelParts.ts';
import { componentMapStore } from '../src/lib/stores/componentMapStore.ts';
import { priorTreesStore } from '../src/lib/stores/priorTreesStore.ts';
import { semanticFieldsStore } from '../src/lib/stores/semanticFieldsStore.ts';
import { removeCharacteristic, renameCharacteristic } from '../src/lib/stores/characteristics.ts';
import type { SemanticField } from '../src/lib/types/semanticFields.ts';
import type { PriorConfig } from '../src/lib/types/priorTrees.ts';

const ORDER = ['Region', 'Typology', 'Heating'];

function assembliesMap(): Record<string, unknown> {
  return {
    Envelope: {
      Assemblies: {
        selector: { source_fields: ['Region'] },
        FacadeAssembly: {},
        FlatRoofAssembly: {},
      },
    },
  };
}

function field(name: string, extra: Partial<SemanticField> = {}): SemanticField {
  return { id: `id-${name}`, name, type: 'stochastic', dataType: 'categorical', options: ['a', 'b'], ...extra };
}

function config(extra: Partial<PriorConfig> = {}): PriorConfig {
  return { registry: { fields: [] }, priors: {}, joints: [], scenarios: [], ...extra };
}

test('ticking a part under an inherited parent creates a child override', () => {
  const facade = 'Envelope.Assemblies.FacadeAssembly';
  const roof = 'Envelope.Assemblies.FlatRoofAssembly';
  const map = setPartForField(assembliesMap(), facade, 'Typology', true, ORDER);

  assert.deepEqual(getSelectorAtPath(map, facade)?.source_fields, ['Region', 'Typology']);
  assert.deepEqual(fieldStatusAtPath(map, roof, 'Region'), { status: 'inherited', from: 'Envelope.Assemblies' });
  assert.equal(fieldStatusAtPath(map, roof, 'Typology').status, 'off');
});

test('a new field goes in at its list position without reordering the rest', () => {
  const path = 'Envelope.Assemblies';
  const start = setPartForField(assembliesMap(), path, 'Heating', true, ORDER);
  const map = setPartForField(start, path, 'Typology', true, ORDER);

  assert.deepEqual(getSelectorAtPath(map, path)?.source_fields, ['Region', 'Typology', 'Heating']);
  assert.equal(setPartForField(map, path, 'Typology', true, ORDER), map);
});

test('unticking only changes the path’s own selector', () => {
  const facade = 'Envelope.Assemblies.FacadeAssembly';
  const map = assembliesMap();

  assert.equal(setPartForField(map, facade, 'Region', false, ORDER), map);
  const cleared = setPartForField(map, 'Envelope.Assemblies', 'Region', false, ORDER);
  assert.equal(getSelectorAtPath(cleared, 'Envelope.Assemblies'), null);
});

test('renameFieldInMap keeps selector order and suffix', () => {
  const map = { Heating: { selector: { source_fields: ['Region', 'Heating'], suffix: 'Main' } } };
  const renamed = renameFieldInMap(map, 'Region', 'Area');

  assert.deepEqual(getSelectorAtPath(renamed, 'Heating'), { source_fields: ['Area', 'Heating'], suffix: 'Main' });
  assert.equal(renameFieldInMap(map, 'Missing', 'X'), map);
});

test('ruleIssues flags labels, inverted and touching ranges, and a missing column', () => {
  const ranged = field('Age', {
    type: 'deterministic',
    dataType: 'numeric',
    options: ['old', 'new'],
    transformationRule: {
      id: 'r',
      type: 'numeric_range',
      sourceColumn: 'year',
      targetField: 'Age',
      numericRanges: [
        { label: 'old', min: 0, max: 1000 },
        { label: 'new', min: 1000, max: 9999 },
        { label: 'minisplits', min: 50, max: 10 },
      ],
    },
  });
  const issues = ruleIssues(ranged);

  assert.ok(issues.includes('Range "minisplits" is not one of the values.'));
  assert.ok(issues.includes('Range "minisplits" starts above where it ends.'));
  assert.ok(issues.some((issue) => issue.includes('"old" and "new" overlap')));
  assert.deepEqual(ruleIssues(field('Typology', { type: 'deterministic' })), ['Choose the GIS column it comes from.']);
  assert.deepEqual(ruleIssues(field('Heating')), []);
});

test('characteristicOrder puts data first, then estimates after what they depend on', () => {
  const fields = [field('Heating'), field('Typology', { type: 'deterministic' }), field('Cooling')];
  const priors = config({ joints: [{ target: 'Heating', condition_on: ['Typology', 'Cooling'], table: {} }] });

  assert.deepEqual(
    characteristicOrder(fields, priors).map((f) => f.name),
    ['Typology', 'Cooling', 'Heating']
  );
  assert.deepEqual(dependentsOf(priors, 'Cooling'), ['Heating']);
});

test('renameInPriorConfig reaches targets, conditions, compound keys and the registry', () => {
  const original = config({
    registry: { fields: [{ name: 'Typology', values: ['a'], dtype: 'categorical' }] },
    priors: {
      'compound.Typology.Age': { sampler: { features_to_concatenate: ['Typology', 'Age'], separator: '.' } },
      wwr: { source_feature: 'compound.Typology.Age', conditions: [], fallback_prior: null },
    },
    joints: [{ target: 'Heating', condition_on: ['Typology'], table: { a: { x: 1 } } }],
  });
  const renamed = renameInPriorConfig(original, 'Typology', 'Kind');

  assert.equal(renamed.registry.fields[0].name, 'Kind');
  assert.deepEqual(renamed.joints[0].condition_on, ['Kind']);
  assert.deepEqual(renamed.joints[0].table, { a: { x: 1 } });
  assert.ok('compound.Kind.Age' in renamed.priors);
  assert.deepEqual(renamed.priors['compound.Kind.Age'], {
    sampler: { features_to_concatenate: ['Kind', 'Age'], separator: '.' },
  });
  assert.equal((renamed.priors.wwr as { source_feature: string }).source_feature, 'compound.Kind.Age');
  assert.equal(renameInPriorConfig(original, 'Nothing', 'X'), original);
});

test('comboBudget counts records per selector and rows per estimate table', () => {
  const fields = [field('Region', { options: ['MA'] }), field('Typology', { options: ['SFH', 'MFH'] })];
  const map = {
    Window: { selector: { source_fields: ['Region', 'Typology'] } },
    DHW: { selector: { source_fields: ['Typology'] } },
  };
  const priors = config({ joints: [{ target: 'Heating', condition_on: ['Typology'], table: {} }] });

  assert.deepEqual(comboBudget(map, fields, priors), { records: 4, estimateRows: 2 });
});

test('otherPaths lists tree paths no named part covers', () => {
  assert.deepEqual(otherPaths(['Envelope', 'Envelope.Window', 'Operations.SpaceUse.Lighting.Schedule']), [
    'Envelope',
    'Operations.SpaceUse.Lighting.Schedule',
  ]);
});

test('renaming and removing a characteristic reaches all three stores', () => {
  semanticFieldsStore.loadFromTemplate({
    Fields: [
      { Name: 'Typology', Options: ['SFH'], Type: 'stochastic', Requires_Prior: true },
      { Name: 'Heating', Options: ['Gas'], Type: 'stochastic', Requires_Prior: true },
    ],
  });
  componentMapStore.setMap({ Heating: { selector: { source_fields: ['Typology', 'Heating'] } } });
  priorTreesStore.setConfig(
    config({
      priors: { Typology: { sampler: { values: ['SFH'], weights: [1] } } },
      joints: [{ target: 'Heating', condition_on: ['Typology'], table: { SFH: { Gas: 1 } } }],
    })
  );

  renameCharacteristic('Typology', 'Kind');

  assert.deepEqual(
    get(semanticFieldsStore).fields.map((f) => f.name),
    ['Kind', 'Heating']
  );
  assert.deepEqual(getSelectorAtPath(get(componentMapStore).map!, 'Heating')?.source_fields, ['Kind', 'Heating']);
  assert.ok('Kind' in get(priorTreesStore).config.priors);
  assert.deepEqual(get(priorTreesStore).config.joints[0].condition_on, ['Kind']);

  removeCharacteristic('Heating');

  assert.deepEqual(
    get(semanticFieldsStore).fields.map((f) => f.name),
    ['Kind']
  );
  assert.deepEqual(getSelectorAtPath(get(componentMapStore).map!, 'Heating')?.source_fields, ['Kind']);
  assert.equal(get(priorTreesStore).config.joints.length, 0);
});

test('defaultSuffix only disambiguates components that share a library table', () => {
  const nodes = {
    'Envelope.Window': { componentType: 'GlazingConstructionSimple' },
    'Envelope.Assemblies.FacadeAssembly': { componentType: 'ConstructionAssembly' },
    'Envelope.Assemblies.FlatRoofAssembly': { componentType: 'ConstructionAssembly' },
    'Operations.SpaceUse.Lighting.Schedule': { componentType: 'Year' },
    'Operations.SpaceUse.Equipment.Schedule': { componentType: 'Year' },
  };

  assert.equal(defaultSuffix('Envelope.Window', nodes), undefined);
  assert.equal(defaultSuffix('Envelope.Assemblies.FacadeAssembly', nodes), 'Facade');
  assert.equal(defaultSuffix('Operations.SpaceUse.Lighting.Schedule', nodes), 'LightingSchedule');

  const map = setPartForField({ Envelope: { Window: {} } }, 'Envelope.Window', 'Region', true, ORDER, 'Win');
  assert.deepEqual(getSelectorAtPath(map, 'Envelope.Window'), { source_fields: ['Region'], suffix: 'Win' });
  const kept = setPartForField(map, 'Envelope.Window', 'Typology', true, ORDER, 'Other');
  assert.equal(getSelectorAtPath(kept, 'Envelope.Window')?.suffix, 'Win');
});

test('a characteristic nothing uses is flagged until a part or an estimate uses it', () => {
  const typology = field('Typology', { type: 'deterministic', transformationRule: { id: 'r', type: 'categorical_mapping', sourceColumn: 'use', targetField: 'Typology', categoricalGroups: [{ groupLabel: 'a', sourceValues: ['x'] }] } });
  const unused = (map: Record<string, unknown> | null, priors: PriorConfig) =>
    characteristicView(typology, map, priors, [typology], ['Envelope.Window']).issues.some((i) => i.startsWith('Not used yet'));

  assert.equal(unused(null, config()), true);
  assert.equal(unused({ Envelope: { Window: { selector: { source_fields: ['Typology'] } } } }, config()), false);
  assert.equal(
    unused(null, config({ joints: [{ target: 'Heating', condition_on: ['Typology'], table: {} }] })),
    false
  );
});
