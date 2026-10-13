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

/**
 * Categorical slots, in validated order, as CSS variables (defined in app.css with
 * separate light/dark steps). Past the eighth, values share the last slot.
 */
export const SERIES_COLORS = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);

/**
 * The same slots as literal hex, for places that can't resolve CSS variables
 * (SVG ids, canvas, xyflow marker definitions). Keep in sync with app.css.
 */
export const SERIES_HEX: Record<'light' | 'dark', string[]> = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
};

/** Number of sequential steps (--seq-0 .. --seq-9), low -> high magnitude. */
const SEQUENTIAL_STEPS = 10;

export function seriesColor(index: number): string {
  return SERIES_COLORS[Math.min(index, SERIES_COLORS.length - 1)];
}

/** The fill for a 0..1 weight. Near-zero stays at the surface so a sparse table reads as sparse. */
export function weightColor(weight: number): string {
  if (!Number.isFinite(weight) || weight <= 0.001) return 'var(--surface)';
  const step = Math.min(SEQUENTIAL_STEPS - 1, Math.floor(weight * SEQUENTIAL_STEPS));
  return `var(--seq-${step})`;
}

/** Ink that stays legible on the cell fill (the dark ramp runs the other way, so this is themed). */
export function weightInk(weight: number): string {
  return weight >= 0.6 ? 'var(--seq-ink-high)' : 'var(--seq-ink-low)';
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
