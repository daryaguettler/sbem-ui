<script lang="ts">
  /**
   * The lookup table, as an editable heatmap.
   *
   * Rows are the combinations that occur in the stock, columns are the target's
   * values, and each cell is both a weight input and a heatmap cell -- the blue
   * fill encodes magnitude so the shape of the prior is readable at a glance,
   * while the number stays editable in place. Cells are always labelled, so the
   * fill is reinforcement rather than the only encoding.
   *
   * Weights are stored as typed. The sampler renormalizes each row, so a row that
   * doesn't sum to 1 still samples correctly; the running total is shown anyway
   * because a row summing to 0.8 is usually a mistake rather than an intent.
   */
  import type { Distribution, GeneratedKey, JointSpec } from '../../types/priorTrees';
  import { distributionTotal, weightColor, weightInk } from '../../utils/priorViz';
  import Icon from '../Icon.svelte';
  import WeightBar from './WeightBar.svelte';
  import PasteOdds from './PasteOdds.svelte';
  import { FALLBACK_KEY, type PastedRow } from '../../utils/pasteOdds';

  export let joint: JointSpec;
  export let values: string[];
  /** Per-key evidence from the generator: how many buildings, and whether the row was estimated. */
  export let evidence: GeneratedKey[] = [];
  export let onCellChange: (key: string, weights: Distribution) => void;
  export let onFallbackChange: (weights: Distribution) => void;
  export let onRemoveRow: (key: string) => void;
  /** Show weights as "buildings out of 100" (natural frequencies) instead of 0–1 shares. */
  export let asCounts = false;

  let filter = '';
  /** The row open as a draggable bar under the table (click its name). */
  let barKey: string | null = null;

  function applyPasted(rows: PastedRow[]) {
    for (const row of rows) {
      if (row.key === FALLBACK_KEY) onFallbackChange(row.weights);
      else if (row.key) onCellChange(row.key, row.weights);
    }
  }
  // Stored weights stay 0–1 shares either way; this only changes what is shown and typed.
  $: scale = asCounts ? 100 : 1;

  function shown(weight: number): number {
    return asCounts ? Math.round(weight * 1000) / 10 : weight;
  }

  $: evidenceByKey = new Map(evidence.map((entry) => [entry.key, entry]));
  $: keys = Object.keys(joint.table)
    .filter((key) => key.toLowerCase().includes(filter.trim().toLowerCase()))
    .sort((a, b) => (evidenceByKey.get(b)?.count ?? 0) - (evidenceByKey.get(a)?.count ?? 0) || a.localeCompare(b));
  $: fallback = joint.fallback ?? {};

  function cellValue(key: string, value: string): number {
    return Number(joint.table[key]?.[value] ?? 0);
  }

  function updateCell(key: string, value: string, raw: string) {
    const weight = Number(raw) / scale;
    if (!Number.isFinite(weight) || weight < 0) return;
    onCellChange(key, { ...joint.table[key], [value]: weight });
  }

  function updateFallback(value: string, raw: string) {
    const weight = Number(raw) / scale;
    if (!Number.isFinite(weight) || weight < 0) return;
    onFallbackChange({ ...fallback, [value]: weight });
  }

  /** Spread a row evenly across the target's values. */
  function levelRow(key: string) {
    const share = values.length ? 1 / values.length : 0;
    onCellChange(key, Object.fromEntries(values.map((value) => [value, Number(share.toFixed(6))])));
  }

  /** Rescale a row so its weights sum to exactly 1, preserving their proportions. */
  function normalizeRow(key: string) {
    const row = joint.table[key] ?? {};
    const total = distributionTotal(row);
    if (total <= 0) return levelRow(key);
    onCellChange(
      key,
      Object.fromEntries(values.map((value) => [value, Number(((Number(row[value]) || 0) / total).toFixed(6))]))
    );
  }
</script>

<div class="table-editor">
  <div class="toolbar">
    <label class="filter">
      <span class="visually-hidden">Filter combinations</span>
      <input type="text" class="input-sm" placeholder="Filter combinations…" bind:value={filter} />
    </label>
    <label class="mode">
      <input type="checkbox" bind:checked={asCounts} />
      Show as buildings out of 100
    </label>
    <PasteOdds {values} keys={Object.keys(joint.table)} separator={joint.separator ?? '.'} onApply={applyPasted} />
    <span class="hint">
      {keys.length} of {Object.keys(joint.table).length}
      {Object.keys(joint.table).length === 1 ? 'combination' : 'combinations'}
    </span>
  </div>

  {#if keys.length === 0}
    <p class="empty">No combinations match this filter.</p>
  {:else}
    <div class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th class="key-col" scope="col">{joint.condition_on.join(' · ')}</th>
            <th class="num" scope="col" title="Buildings in this combination">n</th>
            {#each values as value}
              <th scope="col" class="value-col">{value}</th>
            {/each}
            <th class="num" scope="col">Sum</th>
            <th scope="col"><span class="visually-hidden">Row actions</span></th>
          </tr>
        </thead>
        <tbody>
          {#each keys as key}
            {@const row = joint.table[key] ?? {}}
            {@const total = distributionTotal(row)}
            {@const info = evidenceByKey.get(key)}
            <tr>
              <th scope="row" class="key-col">
                <button type="button" class="key-name" title="Adjust this row by dragging its bar" aria-expanded={barKey === key} onclick={() => (barKey = barKey === key ? null : key)}>{key.split('.').join(' · ')}</button>
                {#if info}
                  <span class="key-source" class:estimated={info.estimated}>
                    {info.source === 'resstock' ? 'from ResStock' : info.estimated ? `estimated from ${info.supportingCount} buildings` : 'uses “Everything else”'}
                  </span>
                {/if}
              </th>
              <td class="num muted">{info ? info.count.toLocaleString() : '—'}</td>
              {#each values as value}
                {@const weight = cellValue(key, value)}
                <td class="cell" style="background: {weightColor(weight)};">
                  <input
                    type="number"
                    min="0"
                    max={scale}
                    step={asCounts ? 1 : 0.01}
                    style="color: {weightInk(weight)};"
                    value={shown(weight)}
                    aria-label="{key} · {value}"
                    onchange={(event) => updateCell(key, value, event.currentTarget.value)}
                  />
                </td>
              {/each}
              <td class="num muted" class:off={Math.abs(total - 1) > 0.005}>{asCounts ? shown(total) : total.toFixed(2)}</td>
              <td class="row-actions">
                <button type="button" class="btn btn-ghost btn-sm" title="Rescale this row to sum to 1" aria-label="Rescale row to sum to 1" onclick={() => normalizeRow(key)}>Σ1</button>
                <button type="button" class="btn btn-ghost btn-sm" title="Spread evenly across all values" aria-label="Spread row evenly" onclick={() => levelRow(key)}>Even</button>
                <button type="button" class="btn btn-ghost btn-sm" title="Remove this combination" aria-label="Remove this combination" onclick={() => onRemoveRow(key)}><Icon name="x" size={14} /></button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  {#if barKey && joint.table[barKey]}
    <div class="row-bar">
      <h4>{barKey.split('.').join(' · ')} <button type="button" class="btn btn-ghost btn-sm" onclick={() => (barKey = null)}>Close</button></h4>
      <WeightBar distribution={joint.table[barKey]} order={values} onChange={(weights) => onCellChange(barKey!, weights)} />
    </div>
  {/if}

  <div class="fallback">
    <div>
      <h4>Everything else <span class="hint">(fallback)</span></h4>
      <p class="hint">
        For buildings whose combination isn't listed above. Without it, those buildings can't be sampled.
      </p>
    </div>
    <WeightBar distribution={fallback} order={values} onChange={onFallbackChange} />
    <div class="field-grid" style="--field-min: 150px">
      {#each values as value}
        <label class="field">
          <span>{value}</span>
          <input
            type="number"
            min="0"
            max={scale}
            step={asCounts ? 1 : 0.01}
            value={shown(Number(fallback[value] ?? 0))}
            onchange={(event) => updateFallback(value, event.currentTarget.value)}
          />
        </label>
      {/each}
    </div>
  </div>
</div>

<style>
  .table-editor {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .filter input {
    width: 240px;
  }

  .mode {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-2);
  }

  .data-table-wrap {
    max-height: 460px;
  }

  thead th {
    z-index: 2;
  }

  .value-col {
    text-align: center;
  }

  /* Row headers stick to the left edge, not the top like the column headers. */
  .key-col {
    position: sticky;
    left: 0;
    z-index: 1;
    min-width: 190px;
    background: var(--surface);
  }

  thead .key-col {
    z-index: 3;
  }

  tbody th.key-col {
    border-bottom-color: var(--border);
    white-space: normal;
  }

  .key-name {
    display: block;
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    font-weight: 600;
    color: var(--text);
    text-align: left;
    text-decoration: underline dotted var(--text-faint);
    cursor: pointer;
  }

  .row-bar {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .row-bar h4 {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .key-source {
    display: block;
    font-size: var(--text-xs);
    font-weight: 300;
    color: var(--text-faint);
  }

  .key-source.estimated {
    color: var(--ok-text);
  }

  .muted {
    color: var(--text-muted);
    white-space: nowrap;
  }

  .off {
    color: var(--warn-text);
    font-weight: 600;
  }

  /* A 2px surface gap keeps neighbouring heatmap fills from reading as one block. */
  .cell {
    min-width: 76px;
    padding: 0;
    border-left: 2px solid var(--surface);
    border-right: 2px solid var(--surface);
  }

  .cell input {
    width: 100%;
    border: none;
    background: transparent;
    padding: var(--space-2);
    text-align: center;
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }

  .cell input:focus {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    background: var(--surface);
    /* beats the inline heatmap ink while editing */
    color: var(--text) !important;
  }

  .row-actions {
    padding: var(--space-1);
    white-space: nowrap;
  }

  .fallback {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4);
    border-radius: var(--radius);
    background: var(--surface-2);
  }

  .fallback h4 {
    margin: 0 0 var(--space-1);
    font-size: var(--text-sm);
    font-weight: 600;
  }
</style>
