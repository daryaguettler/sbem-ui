/**
 * Shared visual language for the prior tree charts.
 *
 * Categorical hues identify a field's values (always in fixed slot order, never
 * cycled by rank) and a single-hue blue ramp encodes weight magnitude in the
 * lookup tables. Both come from the validated default palette; the categorical
 * order is the one that clears the colorblind-separation gates, so slots are
 * assigned by a value's position in the field's declared options and stay put
 * when the set is filtered.
 */

import type { Distribution } from '../types/priorTrees';

/** Categorical slots, in validated order. Past the eighth, values share the last slot. */
export const SERIES_COLORS = [
  '#2a78d6',
  '#eb6834',
  '#1baf7a',
  '#eda100',
  '#e87ba4',
  '#008300',
  '#4a3aa7',
  '#e34948',
];

/** Sequential blue, light -> dark, for weight magnitude. */
const SEQUENTIAL = [
  '#cde2fb',
  '#b7d3f6',
  '#9ec5f4',
  '#86b6ef',
  '#6da7ec',
  '#5598e7',
  '#3987e5',
  '#2a78d6',
  '#256abf',
  '#1c5cab',
];

export function seriesColor(index: number): string {
  return SERIES_COLORS[Math.min(index, SERIES_COLORS.length - 1)];
}

/** The fill for a 0..1 weight. Near-zero stays at the surface so a sparse table reads as sparse. */
export function weightColor(weight: number): string {
  if (!Number.isFinite(weight) || weight <= 0.001) return '#ffffff';
  const step = Math.min(SEQUENTIAL.length - 1, Math.floor(weight * SEQUENTIAL.length));
  return SEQUENTIAL[step];
}

/** Ink that stays legible once the cell fill gets dark. */
export function weightInk(weight: number): string {
  return weight >= 0.6 ? '#ffffff' : '#111827';
}

export function formatShare(value: number): string {
  if (!Number.isFinite(value)) return '-';
  if (value === 0) return '0';
  if (value < 0.01) return '<1%';
  return `${Math.round(value * 100)}%`;
}

export function formatPercent(value: number, digits = 0): string {
  return Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : '-';
}

/** A distribution as ordered segments, so a bar and its legend agree on color. */
export function toSegments(
  distribution: Distribution,
  order: string[]
): Array<{ value: string; weight: number; color: string }> {
  const keys = order.length ? order : Object.keys(distribution);
  return keys.map((value, index) => ({
    value,
    weight: Number(distribution[value] ?? 0),
    color: seriesColor(index),
  }));
}

export function distributionTotal(distribution: Distribution): number {
  return Object.values(distribution).reduce((sum, weight) => sum + (Number(weight) || 0), 0);
}
