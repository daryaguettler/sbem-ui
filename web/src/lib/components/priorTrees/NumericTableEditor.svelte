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
      <span class="sr-only">Filter combinations</span>
      <input type="text" placeholder="Filter combinations..." bind:value={filter} />
    </label>
    <span class="count">
      {rows.length} of {prior.conditions.length}
      {prior.conditions.length === 1 ? 'combination' : 'combinations'}
    </span>
  </div>

  {#if rows.length === 0}
    <p class="empty">No combinations match this filter.</p>
  {:else}
    <div class="grid-scroll">
      <table>
        <thead>
          <tr>
            <th class="key-col" scope="col">{prior.source_feature.replace('compound.', '')}</th>
            <th class="count-col" scope="col" title="Buildings in this combination">n</th>
            <th class="plot-col" scope="col">{target} (mean ± sd)</th>
            <th scope="col">Mean</th>
            <th scope="col">SD</th>
            <th scope="col">Min</th>
            <th scope="col">Max</th>
            <th class="actions-col" scope="col"><span class="sr-only">Row actions</span></th>
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
                      : 'inherited from fallback'}
                  </span>
                {/if}
              </th>
              <td class="count-col">{row.info ? row.info.count.toLocaleString() : '—'}</td>
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
              <td><input type="number" step="0.01" value={row.normal.mean}
                   aria-label="{row.key} mean"
                   onchange={(e) => update(row.key, 'mean', e.currentTarget.value)} /></td>
              <td><input type="number" step="0.01" min="0" value={row.normal.std}
                   aria-label="{row.key} standard deviation"
                   onchange={(e) => update(row.key, 'std', e.currentTarget.value)} /></td>
              <td><input type="number" step="0.01" value={row.normal.clip_min ?? ''} placeholder="none"
                   aria-label="{row.key} minimum"
                   onchange={(e) => update(row.key, 'clip_min', e.currentTarget.value)} /></td>
              <td><input type="number" step="0.01" value={row.normal.clip_max ?? ''} placeholder="none"
                   aria-label="{row.key} maximum"
                   onchange={(e) => update(row.key, 'clip_max', e.currentTarget.value)} /></td>
              <td class="actions-col">
                <button type="button" class="remove" title="Remove this combination"
                        onclick={() => onRemove(row.key)}>×</button>
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
    <div class="fallback-header">
      <h4>Fallback</h4>
      <p>
        For buildings whose combination isn't listed above. Without it, those buildings can't be sampled.
      </p>
    </div>
    <div class="fallback-inputs">
      <label><span>Mean</span>
        <input type="number" step="0.01" value={fallback.mean}
               onchange={(e) => updateFallback('mean', e.currentTarget.value)} /></label>
      <label><span>SD</span>
        <input type="number" step="0.01" min="0" value={fallback.std}
               onchange={(e) => updateFallback('std', e.currentTarget.value)} /></label>
      <label><span>Min</span>
        <input type="number" step="0.01" value={fallback.clip_min ?? ''} placeholder="none"
               onchange={(e) => updateFallback('clip_min', e.currentTarget.value)} /></label>
      <label><span>Max</span>
        <input type="number" step="0.01" value={fallback.clip_max ?? ''} placeholder="none"
               onchange={(e) => updateFallback('clip_max', e.currentTarget.value)} /></label>
    </div>
  </div>
</div>

<style>
  .numeric-editor {
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
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    font-size: 13px;
    width: 240px;
  }

  .count {
    font-size: 12px;
    color: var(--text-muted);
  }

  .grid-scroll {
    overflow: auto;
    max-height: 460px;
    border: 1px solid var(--border);
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
    background: var(--surface-2);
    border-bottom: 1px solid var(--border);
    padding: 8px;
    text-align: left;
    font-weight: 600;
    color: var(--text-2);
    white-space: nowrap;
  }

  tbody th,
  tbody td {
    border-bottom: 1px solid var(--surface-3);
    padding: 4px 6px;
    vertical-align: middle;
  }

  .key-col {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--surface);
    min-width: 180px;
    padding: 6px 10px !important;
    text-align: left;
  }

  thead .key-col {
    z-index: 3;
    background: var(--surface-2);
  }

  .key-name {
    display: block;
    font-weight: 600;
    color: var(--text);
  }

  .key-source {
    display: block;
    font-size: 10px;
    color: var(--text-faint);
  }

  .key-source.estimated {
    color: var(--ok-text);
  }

  .count-col {
    text-align: right;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
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
    border-radius: 3px;
  }

  /* The ±1 sd band, with the mean marked on top of it. */
  .spread {
    position: absolute;
    top: 6px;
    height: 6px;
    min-width: 2px;
    background: var(--seq-2);
    border-radius: 3px;
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
    height: 14px;
    border-top: 1px solid var(--border);
    font-size: 10px;
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
    font-size: 10px;
    color: var(--text-faint);
  }

  tbody input {
    width: 86px;
    padding: 5px 6px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  tbody input:focus {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .actions-col {
    white-space: nowrap;
  }

  .actions-col .remove {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--err-text);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
    cursor: pointer;
    font-weight: 400;
  }

  .actions-col .remove:hover {
    background: var(--err-bg);
  }

  .empty {
    margin: 0;
    font-size: 13px;
    color: var(--text-muted);
  }

  .fallback {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-2);
  }

  .fallback-header h4 {
    margin: 0 0 4px;
    font-size: 13px;
  }

  .fallback-header p {
    margin: 0;
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.5;
  }

  .fallback-inputs {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 8px;
  }

  .fallback-inputs label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 11px;
    color: var(--text-2);
  }

  .fallback-inputs input {
    padding: 5px 8px;
    border: 1px solid var(--border-strong);
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
