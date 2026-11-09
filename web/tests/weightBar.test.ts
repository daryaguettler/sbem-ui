// Dragging a boundary of the odds bar moves weight only between its two neighbours.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { moveBoundary } from '../src/lib/utils/priorViz.ts';

const close = (actual: number[], expected: number[]) =>
  actual.forEach((value, i) => assert.ok(Math.abs(value - expected[i]) < 1e-9, `${actual} != ${expected}`));

test('a boundary moves weight between its neighbours, snapped to 1%', () => {
  close(moveBoundary([0.2, 0.3, 0.5], 0, 0.354), [0.35, 0.15, 0.5]);
  close(moveBoundary([0.2, 0.3, 0.5], 1, 0.4), [0.2, 0.2, 0.6]);
});

test('a boundary cannot pass its neighbours', () => {
  close(moveBoundary([0.2, 0.3, 0.5], 1, 0.05), [0.2, 0, 0.8]);
  close(moveBoundary([0.2, 0.3, 0.5], 0, 0.9), [0.5, 0, 0.5]);
  close(moveBoundary([0.2, 0.3, 0.5], 0, -1), [0, 0.5, 0.5]);
});
