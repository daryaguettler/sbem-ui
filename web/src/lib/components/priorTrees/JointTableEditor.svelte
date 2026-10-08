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
  import WeightBar from './WeightBar.svelte';

  export let joint: JointSpec;
  export let values: string[];
  /** Per-key evidence from the generator: how many buildings, and whether the row was estimated. */
  export let evidence: GeneratedKey[] = [];
  export let onCellChange: (key: string, weights: Distribution) => void;
  export let onFallbackChange: (weights: Distribution) => void;
  export let onRemoveRow: (key: string) => void;

  let filter = '';

  $: evidenceByKey = new Map(evidence.map((entry) => [entry.key, entry]));
  $: keys = Object.keys(joint.table)
    .filter((key) => key.toLowerCase().includes(filter.trim().toLowerCase()))
    .sort((a, b) => (evidenceByKey.get(b)?.count ?? 0) - (evidenceByKey.get(a)?.count ?? 0) || a.localeCompare(b));
  $: fallback = joint.fallback ?? {};

  function cellValue(key: string, value: string): number {
    return Number(joint.table[key]?.[value] ?? 0);
  }

  function updateCell(key: string, value: string, raw: string) {
    const weight = Number(raw);
    if (!Number.isFinite(weight) || weight < 0) return;
    onCellChange(key, { ...joint.table[key], [value]: weight });
  }

  function updateFallback(value: string, raw: string) {
    const weight = Number(raw);
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
      <span class="sr-only">Filter combinations</span>
      <input type="text" placeholder="Filter combinations..." bind:value={filter} />
    </label>
    <span class="count">
      {keys.length} of {Object.keys(joint.table).length}
      {Object.keys(joint.table).length === 1 ? 'combination' : 'combinations'}
    </span>
  </div>

  {#if keys.length === 0}
    <p class="empty">No combinations match this filter.</p>
  {:else}
    <div class="grid-scroll">
      <table>
        <thead>
          <tr>
            <th class="key-col" scope="col">{joint.condition_on.join(' · ')}</th>
            <th class="count-col" scope="col" title="Buildings in this combination">n</th>
            {#each values as value}
              <th scope="col" class="value-col">{value}</th>
            {/each}
            <th class="total-col" scope="col">Sum</th>
            <th class="actions-col" scope="col"><span class="sr-only">Row actions</span></th>
          </tr>
        </thead>
        <tbody>
          {#each keys as key}
            {@const row = joint.table[key] ?? {}}
            {@const total = distributionTotal(row)}
            {@const info = evidenceByKey.get(key)}
            <tr>
              <th scope="row" class="key-col">
                <span class="key-name">{key}</span>
                {#if info}
                  <span class="key-source" class:estimated={info.estimated}>
                    {info.estimated ? `estimated from ${info.supportingCount} buildings` : 'inherited from fallback'}
                  </span>
                {/if}
              </th>
              <td class="count-col">{info ? info.count.toLocaleString() : '—'}</td>
              {#each values as value}
                {@const weight = cellValue(key, value)}
                <td class="cell" style="background: {weightColor(weight)};">
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    style="color: {weightInk(weight)};"
                    value={weight}
                    aria-label="{key} · {value}"
                    onchange={(event) => updateCell(key, value, event.currentTarget.value)}
                  />
                </td>
              {/each}
              <td class="total-col" class:off={Math.abs(total - 1) > 0.005}>{total.toFixed(2)}</td>
              <td class="actions-col">
                <button type="button" title="Rescale this row to sum to 1" onclick={() => normalizeRow(key)}>≡</button>
                <button type="button" title="Spread evenly" onclick={() => levelRow(key)}>÷</button>
                <button type="button" class="remove" title="Remove this combination" onclick={() => onRemoveRow(key)}>×</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <div class="fallback">
    <div class="fallback-header">
      <h4>Fallback</h4>
      <p>
        Used for any building whose combination isn't in the table above. Without one, an
        unlisted combination fails to sample.
      </p>
    </div>
    <WeightBar distribution={fallback} order={values} />
    <div class="fallback-inputs">
      {#each values as value}
        <label>
          <span>{value}</span>
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={Number(fallback[value] ?? 0)}
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
    gap: 16px;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .filter input {
    padding: 6px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    width: 240px;
  }

  .count {
    font-size: 12px;
    color: #6b7280;
  }

  .grid-scroll {
    overflow: auto;
    max-height: 460px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }

  table {
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    font-size: 12px;
  }

  thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    padding: 8px;
    text-align: left;
    font-weight: 600;
    color: #374151;
    white-space: nowrap;
  }

  .value-col {
    text-align: center;
  }

  tbody th,
  tbody td {
    border-bottom: 1px solid #f3f4f6;
    padding: 0;
  }

  .key-col {
    position: sticky;
    left: 0;
    z-index: 1;
    background: #ffffff;
    min-width: 190px;
    padding: 6px 10px !important;
    text-align: left;
    vertical-align: middle;
  }

  thead .key-col {
    z-index: 3;
    background: #f9fafb;
  }

  .key-name {
    display: block;
    font-weight: 600;
    color: #111827;
  }

  .key-source {
    display: block;
    font-size: 10px;
    color: #9ca3af;
  }

  .key-source.estimated {
    color: #15803d;
  }

  .count-col {
    padding: 6px 8px !important;
    text-align: right;
    color: #6b7280;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  /* A 2px surface gap keeps neighbouring heatmap fills from reading as one block. */
  .cell {
    border-left: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    min-width: 76px;
  }

  .cell input {
    width: 100%;
    border: none;
    background: transparent;
    padding: 8px 6px;
    text-align: center;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }

  .cell input:focus {
    outline: 2px solid #2563eb;
    outline-offset: -2px;
    background: #ffffff;
    color: #111827 !important;
  }

  .total-col {
    padding: 6px 10px !important;
    text-align: right;
    color: #6b7280;
    font-variant-numeric: tabular-nums;
  }

  .total-col.off {
    color: #b45309;
    font-weight: 600;
  }

  .actions-col {
    padding: 4px 6px !important;
    white-space: nowrap;
  }

  .actions-col button {
    border: 1px solid #e5e7eb;
    background: #ffffff;
    color: #4b5563;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
    cursor: pointer;
    font-weight: 400;
  }

  .actions-col button:hover {
    background: #f3f4f6;
  }

  .actions-col .remove {
    color: #b91c1c;
  }

  .empty {
    margin: 0;
    font-size: 13px;
    color: #6b7280;
  }

  .fallback {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #f9fafb;
  }

  .fallback-header h4 {
    margin: 0 0 4px;
    font-size: 13px;
  }

  .fallback-header p {
    margin: 0;
    font-size: 12px;
    color: #6b7280;
    line-height: 1.5;
  }

  .fallback-inputs {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
  }

  .fallback-inputs label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 11px;
    color: #4b5563;
  }

  .fallback-inputs input {
    padding: 5px 8px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
</style>
