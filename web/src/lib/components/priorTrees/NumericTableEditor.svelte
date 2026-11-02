<script lang="ts">
  /**
   * A conditioned numeric prior: one clipped normal per combination.
   *
   * The chart is a dot plot with error bars rather than a heatmap -- what matters
   * for a numeric prior is where each combination's mean sits relative to the
   * others, and how wide it is. All rows share one axis so the comparison is
   * direct, and the mean is labelled on every row so the read never depends on
   * pixel position alone.
   */
  import type { ConditionalPriorSpec, GeneratedKey } from '../../types/priorTrees';
  import { asNormal } from '../../types/priorTrees';
  import Icon from '../Icon.svelte';

  export let prior: ConditionalPriorSpec;
  export let target: string;
  /** Per-key evidence from the generator: how many buildings, and whether it was fitted. */
  export let evidence: GeneratedKey[] = [];
  export let onSamplerChange: (matchVal: string, sampler: Record<string, unknown>) => void;
  export let onFallbackChange: (sampler: Record<string, unknown>) => void;
  export let onRemove: (matchVal: string) => void;

  let filter = '';

  $: evidenceByKey = new Map(evidence.map((entry) => [entry.key, entry]));
  $: rows = prior.conditions
    .filter((condition) => String(condition.match_val).toLowerCase().includes(filter.trim().toLowerCase()))
    .map((condition) => ({
      key: String(condition.match_val),
      normal: asNormal(condition.sampler),
      info: evidenceByKey.get(String(condition.match_val)),
    }));
  $: fallback = asNormal(prior.fallback_prior);

  /** One shared axis across every row, padded so a mean never sits on the edge. */
  $: domain = (() => {
    const all = [...rows.map((row) => row.normal), fallback];
    const lows = all.map((n) => (n.clip_min ?? n.mean - 3 * n.std));
    const highs = all.map((n) => (n.clip_max ?? n.mean + 3 * n.std));
    const min = Math.min(...lows, ...all.map((n) => n.mean - n.std));
    const max = Math.max(...highs, ...all.map((n) => n.mean + n.std));
    const span = max - min || 1;
    return { min: min - span * 0.04, max: max + span * 0.04 };
  })();

  function position(value: number): number {
    const span = domain.max - domain.min || 1;
    return Math.min(100, Math.max(0, ((value - domain.min) / span) * 100));
  }

  function update(matchVal: string, field: string, raw: string) {
    const parsed = raw === '' ? null : Number(raw);
    if (parsed !== null && !Number.isFinite(parsed)) return;
    const condition = prior.conditions.find((entry) => String(entry.match_val) === matchVal);
    if (!condition) return;
    onSamplerChange(matchVal, { ...condition.sampler, [field]: parsed });
  }

  function updateFallback(field: string, raw: string) {
    const parsed = raw === '' ? null : Number(raw);
    if (parsed !== null && !Number.isFinite(parsed)) return;
    onFallbackChange({ ...(prior.fallback_prior ?? {}), [field]: parsed });
  }

  function tick(value: number): string {
    const span = domain.max - domain.min;
    return span < 1 ? value.toFixed(3) : value.toFixed(1);
  }
</script>

<div class="numeric-editor">
  <div class="toolbar">
    <label class="filter">
      <span class="visually-hidden">Filter combinations</span>
      <input type="text" class="input-sm" placeholder="Filter combinations…" bind:value={filter} />
    </label>
    <span class="hint">
      {rows.length} of {prior.conditions.length}
      {prior.conditions.length === 1 ? 'combination' : 'combinations'}
    </span>
  </div>

  {#if rows.length === 0}
    <p class="empty">No combinations match this filter.</p>
  {:else}
    <div class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th class="key-col" scope="col">{prior.source_feature.replace('compound.', '')}</th>
            <th class="num" scope="col" title="Buildings in this combination">n</th>
            <th class="plot-col" scope="col">{target} (mean ± sd)</th>
            <th scope="col" class="num">Mean</th>
            <th scope="col" class="num">SD</th>
            <th scope="col" class="num">Min</th>
            <th scope="col" class="num">Max</th>
            <th scope="col"><span class="visually-hidden">Row actions</span></th>
          </tr>
        </thead>
        <tbody>
          {#each rows as row}
            <tr>
              <th scope="row" class="key-col">
                <span class="key-name">{row.key}</span>
                {#if row.info}
                  <span class="key-source" class:estimated={row.info.estimated}>
                    {row.info.estimated
                      ? `fitted to ${row.info.supportingCount} buildings`
                      : 'uses “Everything else”'}
                  </span>
                {/if}
              </th>
              <td class="num muted">{row.info ? row.info.count.toLocaleString() : '—'}</td>
              <td class="plot-col">
                <span
                  class="plot"
                  role="img"
                  aria-label="{row.key}: mean {row.normal.mean}, sd {row.normal.std}"
                >
                  <span
                    class="spread"
                    style="left: {position(row.normal.mean - row.normal.std)}%;
                           width: {position(row.normal.mean + row.normal.std) -
                             position(row.normal.mean - row.normal.std)}%;"
                  ></span>
                  <span class="dot" style="left: {position(row.normal.mean)}%;"></span>
                </span>
              </td>
              <td class="num"><input type="number" class="input-sm" step="0.01" value={row.normal.mean}
                   aria-label="{row.key} mean"
                   onchange={(e) => update(row.key, 'mean', e.currentTarget.value)} /></td>
              <td class="num"><input type="number" class="input-sm" step="0.01" min="0" value={row.normal.std}
                   aria-label="{row.key} standard deviation"
                   onchange={(e) => update(row.key, 'std', e.currentTarget.value)} /></td>
              <td class="num"><input type="number" class="input-sm" step="0.01" value={row.normal.clip_min ?? ''} placeholder="none"
                   aria-label="{row.key} minimum"
                   onchange={(e) => update(row.key, 'clip_min', e.currentTarget.value)} /></td>
              <td class="num"><input type="number" class="input-sm" step="0.01" value={row.normal.clip_max ?? ''} placeholder="none"
                   aria-label="{row.key} maximum"
                   onchange={(e) => update(row.key, 'clip_max', e.currentTarget.value)} /></td>
              <td class="row-actions">
                <button type="button" class="btn btn-ghost btn-sm" title="Remove this combination"
                        aria-label="Remove this combination"
                        onclick={() => onRemove(row.key)}><Icon name="x" size={14} /></button>
              </td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <td class="key-col axis-label">scale</td>
            <td></td>
            <td class="plot-col">
              <span class="axis">
                <span class="axis-min">{tick(domain.min)}</span>
                <span class="axis-max">{tick(domain.max)}</span>
              </span>
            </td>
            <td colspan="5"></td>
          </tr>
        </tfoot>
      </table>
    </div>
  {/if}

  <div class="fallback">
    <div>
      <h4>Everything else <span class="hint">(fallback)</span></h4>
      <p class="hint">
        For buildings whose combination isn't listed above. Without it, those buildings can't be sampled.
      </p>
    </div>
    <div class="field-grid" style="--field-min: 130px">
      <label class="field"><span>Mean</span>
        <input type="number" step="0.01" value={fallback.mean}
               onchange={(e) => updateFallback('mean', e.currentTarget.value)} /></label>
      <label class="field"><span>SD</span>
        <input type="number" step="0.01" min="0" value={fallback.std}
               onchange={(e) => updateFallback('std', e.currentTarget.value)} /></label>
      <label class="field"><span>Min</span>
        <input type="number" step="0.01" value={fallback.clip_min ?? ''} placeholder="none"
               onchange={(e) => updateFallback('clip_min', e.currentTarget.value)} /></label>
      <label class="field"><span>Max</span>
        <input type="number" step="0.01" value={fallback.clip_max ?? ''} placeholder="none"
               onchange={(e) => updateFallback('clip_max', e.currentTarget.value)} /></label>
    </div>
  </div>
</div>

<style>
  .numeric-editor {
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

  .data-table-wrap {
    max-height: 460px;
  }

  thead th {
    z-index: 2;
  }

  tbody td {
    padding: var(--space-1) var(--space-2);
  }

  /* Row headers stick to the left edge, not the top like the column headers. */
  .key-col {
    position: sticky;
    left: 0;
    z-index: 1;
    min-width: 180px;
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
    font-weight: 600;
    color: var(--text);
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

  .plot-col {
    min-width: 200px;
    width: 34%;
  }

  .plot {
    position: relative;
    display: block;
    height: 18px;
    background: var(--surface-2);
    border-radius: var(--radius-sm);
  }

  /* The ±1 sd band, with the mean marked on top of it. */
  .spread {
    position: absolute;
    top: 6px;
    height: 6px;
    min-width: 2px;
    background: var(--seq-2);
    border-radius: var(--radius-sm);
  }

  .dot {
    position: absolute;
    top: 4px;
    width: 10px;
    height: 10px;
    margin-left: -5px;
    border-radius: 50%;
    background: var(--series-1);
    border: 2px solid var(--surface);
  }

  .axis {
    position: relative;
    display: block;
    height: var(--space-5);
    border-top: 1px solid var(--border);
    font-size: var(--text-xs);
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .axis-min {
    position: absolute;
    left: 0;
  }

  .axis-max {
    position: absolute;
    right: 0;
  }

  .axis-label {
    font-size: var(--text-xs);
    color: var(--text-faint);
  }

  tbody input {
    width: 86px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .row-actions {
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
