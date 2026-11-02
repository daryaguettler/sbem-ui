// Run with `make test-web`.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { extraTopLevelKeys } from '../src/lib/utils/semanticFieldsExtras.ts';

test('keeps globi keys the editor does not manage', () => {
  const doc = {
    Name: 'Test Region Model',
    Fields: [{ Name: 'Region', Options: ['TestRegion'] }],
    Building_ID_col: 'id',
    Num_Floors_col: 'num_storeys',
    Height_col: 'height',
    WWR_col: 'wwr',
  };
  assert.deepEqual(extraTopLevelKeys(doc), { Height_col: 'height', WWR_col: 'wwr' });
});
