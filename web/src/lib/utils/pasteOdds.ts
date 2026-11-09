/**
 * Odds pasted from a spreadsheet. A copied block of cells arrives tab-separated: an optional
 * header row naming the values, an optional first column naming the combination
 * ("pre_1975 · Gas", "pre_1975.Gas" or "pre_1975 / Gas"; "Everything else" for the fallback),
 * and shares as decimals or percentages. A single distribution can also be two columns,
 * value and share. Every row is rescaled to add up to 1.
 */
import type { Distribution } from '../types/priorTrees';

/** The key a row gets when it is labelled "Everything else" (the fallback). */
export const FALLBACK_KEY = '__fallback__';
const FALLBACK_NAMES = new Set(['everything else', 'fallback', 'other', 'else', '*']);

export interface PastedRow {
  /** The combination's key, FALLBACK_KEY, or null for an unlabelled row. */
  key: string | null;
  weights: Distribution;
}

export interface PastedOdds {
  rows: PastedRow[];
  warnings: string[];
}

const norm = (text: string) => text.trim().toLowerCase().replace(/\s+/g, ' ');
const labelParts = (label: string) => label.split(/\s*[·.|/]\s*/).map(norm).filter(Boolean).join('|');

function cellsOf(line: string): string[] {
  if (line.includes('\t')) return line.split('\t');
  if (line.includes(';')) return line.split(';');
  return [line.trim()];
}

/** A share as typed: "0.25", "25%", "25", "0,25" (decimal comma). Null if not a number. */
export function parseShare(cell: string): number | null {
  let text = cell.trim().replace(/%$/, '').trim();
  if (/^-?\d+,\d+$/.test(text)) text = text.replace(',', '.');
  if (text === '' || !/^-?\d*\.?\d+(e-?\d+)?$/i.test(text)) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function normalized(weights: Distribution): Distribution | null {
  const total = Object.values(weights).reduce((sum, w) => sum + w, 0);
  if (!(total > 0)) return null;
  return Object.fromEntries(Object.entries(weights).map(([value, w]) => [value, Number((w / total).toFixed(6))]));
}

/**
 * Read pasted odds for a target with `values`; `keys` are the combinations of the table
 * (empty for odds that are the same for every building), joined by `separator`.
 */
export function parsePastedOdds(text: string, values: string[], keys: string[] = [], separator = '.'): PastedOdds {
  const warnings: string[] = [];
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== '').map(cellsOf);
  const valueByName = new Map(values.map((value) => [norm(value), value]));
  const keyByParts = new Map(keys.map((key) => [labelParts(key.split(separator).join('|')), key]));
  if (lines.length === 0) return { rows: [], warnings: ['Nothing to paste.'] };

  // value <tab> share, one value per line: a single distribution
  const pairs = lines.filter((cells) => cells.length >= 2 && valueByName.has(norm(cells[0])));
  if (pairs.length > 0 && pairs.length === lines.filter((cells) => parseShare(cells[cells.length - 1]) !== null).length) {
    const weights: Distribution = Object.fromEntries(values.map((value) => [value, 0]));
    for (const cells of pairs) weights[valueByName.get(norm(cells[0]))!] = parseShare(cells[1]) ?? 0;
    const row = normalized(weights);
    return row ? { rows: [{ key: null, weights: row }], warnings } : { rows: [], warnings: ['The shares add up to 0.'] };
  }

  // a header row names the values; without one, the numbers follow the values' order
  const header = lines[0];
  const headerColumns = header.map((cell) => valueByName.get(norm(cell)) ?? null);
  const hasHeader = headerColumns.some(Boolean);
  if (hasHeader) {
    // the first cell may be the label column's title, so only later cells count
    const unknown = header.slice(1).filter((cell, i) => cell.trim() && !headerColumns[i + 1]);
    if (unknown.length) warnings.push(`Not values of this characteristic, ignored: ${unknown.join(', ')}.`);
    const missing = values.filter((value) => !headerColumns.includes(value));
    if (missing.length) warnings.push(`No column for ${missing.join(', ')}; they get 0.`);
  }

  const rows: PastedRow[] = [];
  for (const cells of hasHeader ? lines.slice(1) : lines) {
    const labelled = parseShare(cells[0]) === null;
    const label = labelled ? cells[0].trim() : null;
    const weights: Distribution = Object.fromEntries(values.map((value) => [value, 0]));
    cells.forEach((cell, i) => {
      if (labelled && i === 0) return;
      const value = hasHeader ? headerColumns[i] : values[i - (labelled ? 1 : 0)];
      const share = parseShare(cell);
      if (value && share !== null) weights[value] = share;
    });

    let key: string | null = null;
    if (label !== null) {
      if (FALLBACK_NAMES.has(norm(label))) key = FALLBACK_KEY;
      else if (keys.length === 0) key = null;
      else {
        key = keyByParts.get(labelParts(label)) ?? null;
        if (key === null) {
          warnings.push(`No combination called “${label}”; skipped.`);
          continue;
        }
      }
    } else if (keys.length > 0) {
      warnings.push('A row without a combination name in its first column was skipped.');
      continue;
    }

    const row = normalized(weights);
    if (row) rows.push({ key, weights: row });
    else warnings.push(`${label ? `“${label}”` : 'A row'} adds up to 0; skipped.`);
  }
  return { rows, warnings };
}
