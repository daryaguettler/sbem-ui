<script lang="ts">
  /**
   * What the prior actually produces.
   *
   * The draws run over the project's own buildings, so the marginal answers "what
   * share of *my* stock ends up with each value" rather than an average over an
   * imaginary uniform stock. The per-condition breakdown underneath is the part
   * that shows a joint working: if conditioning changed nothing, every row of it
   * looks the same.
   */
  import type { SampleSummary } from '../../types/priorTrees';
  import { formatPercent, formatShare, seriesColor, weightColor, weightInk } from '../../utils/priorViz';

  export let sample: SampleSummary;

  let expanded: Record<string, boolean> = {};

  function toggle(feature: string) {
    expanded = { ...expanded, [feature]: !expanded[feature] };
  }

  /** Position a value on the shared 0-100% axis of a numeric breakdown. */
  function scale(value: number, lo: number, hi: number): number {
    const span = hi - lo || 1;
    return Math.min(100, Math.max(0, ((value - lo) / span) * 100));
  }

  /** A stable slot per value, independent of how a given sample ranked it. */
  function colorScale(distribution: { value: string }[]): (value: string) => string {
    const order = distribution.map((entry) => entry.value).sort((a, b) => a.localeCompare(b));
    return (value: string) => seriesColor(Math.max(0, order.indexOf(value)));
  }
</script>

<div class="preview">
  <p class="context">
    {sample.n.toLocaleString()} buildings sampled
    {#if sample.contextSource === 'gis'}
      over your stock, drawing {sample.contextFields.join(', ')} from
      {sample.contextRowCount.toLocaleString()} GIS rows.
    {:else}
      (no conditioning fields, so no GIS context was needed).
    {/if}
    Seed {sample.seed ?? 'random'}.
  </p>

  {#each sample.distributions as distribution}
    <section class="feature">
      <header>
        <h4>{distribution.feature}</h4>
        <span class="kind">
          {distribution.kind === 'conditional'
            ? `conditioned on ${distribution.dependsOn.map((d) => d.replace('compound.', '')).join(', ')}`
            : 'unconditioned'}
        </span>
      </header>

      {#if distribution.dtype === 'numeric' && distribution.histogram}
        {@const histogram = distribution.histogram}
        {@const peak = Math.max(...histogram.bins.map((bin) => bin.count), 1)}
        <div class="histogram" role="img" aria-label="{distribution.feature} distribution">
          {#each histogram.bins as bin}
            <div
              class="bin"
              style="height: {(bin.count / peak) * 100}%;"
              title="{bin.start.toFixed(2)}–{bin.end.toFixed(2)}: {bin.count}"
            ></div>
          {/each}
        </div>
        <p class="stats">
          mean {histogram.mean.toFixed(3)} · sd {histogram.std.toFixed(3)} · range
          {histogram.min.toFixed(2)}–{histogram.max.toFixed(2)}
        </p>

        {#if distribution.numericBreakdown}
          {@const numeric = distribution.numericBreakdown}
          {@const lo = Math.min(...numeric.rows.map((row) => row.mean - row.std))}
          {@const hi = Math.max(...numeric.rows.map((row) => row.mean + row.std))}
          <button type="button" class="toggle" onclick={() => toggle(distribution.feature)}>
            {expanded[distribution.feature] ? 'Hide' : 'Show'} breakdown by
            {numeric.field.replace('compound.', '')}
            ({numeric.rows.length} {numeric.rows.length === 1 ? 'combination' : 'combinations'})
          </button>

          {#if expanded[distribution.feature]}
            <!-- One shared axis per row, so the conditional means compare directly. -->
            <ul class="numeric-rows">
              {#each numeric.rows as row}
                <li>
                  <span class="value-name" title={row.key}>{row.key}</span>
                  <span class="plot" role="img"
                        aria-label="{row.key}: mean {row.mean.toFixed(3)}, sd {row.std.toFixed(3)}">
                    <span
                      class="spread"
                      style="left: {scale(row.mean - row.std, lo, hi)}%;
                             width: {scale(row.mean + row.std, lo, hi) - scale(row.mean - row.std, lo, hi)}%;"
                    ></span>
                    <span class="dot" style="left: {scale(row.mean, lo, hi)}%;"></span>
                  </span>
                  <span class="value-share">{row.mean.toFixed(3)}</span>
                  <span class="row-count">n={row.count.toLocaleString()}</span>
                </li>
              {/each}
            </ul>
            <p class="stats axis-note">
              scale {lo.toFixed(3)} – {hi.toFixed(3)} · dot is the mean, band is ±1 sd
            </p>
          {/if}
        {/if}
      {:else}
        {@const colorOf = colorScale(distribution.marginal)}
        <ul class="marginal">
          {#each distribution.marginal as entry}
            <li>
              <span class="value-name">{entry.value}</span>
              <span class="bar-track">
                <span class="bar-fill" style="width: {entry.share * 100}%; background: {colorOf(entry.value)};"></span>
              </span>
              <span class="value-share">{formatPercent(entry.share, 1)}</span>
            </li>
          {/each}
        </ul>

        {#if distribution.breakdown}
          {@const breakdown = distribution.breakdown}
          <button type="button" class="toggle" onclick={() => toggle(distribution.feature)}>
            {expanded[distribution.feature] ? 'Hide' : 'Show'} breakdown by
            {breakdown.field.replace('compound.', '')}
            ({breakdown.rows.length} {breakdown.rows.length === 1 ? 'combination' : 'combinations'})
          </button>

          {#if expanded[distribution.feature]}
            <div class="breakdown-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{breakdown.field.replace('compound.', '')}</th>
                    <th scope="col" class="count">n</th>
                    {#each breakdown.values as value}
                      <th scope="col" class="value-head">
                        <span class="swatch" style="background: {colorOf(value)};"></span>
                        {value}
                      </th>
                    {/each}
                  </tr>
                </thead>
                <tbody>
                  {#each breakdown.rows as row}
                    <tr>
                      <th scope="row">{row.key}</th>
                      <td class="count">{row.count.toLocaleString()}</td>
                      {#each row.shares as share}
                        <td
                          class="cell"
                          style="background: {weightColor(share)}; color: {weightInk(share)};"
                        >{formatShare(share)}</td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        {/if}
      {/if}
    </section>
  {/each}
</div>

<style>
  .preview {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .context {
    margin: 0;
    font-size: 13px;
    color: #4b5563;
    line-height: 1.5;
  }

  .feature {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-top: 16px;
    border-top: 1px solid #f3f4f6;
  }

  .feature header {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }

  .feature h4 {
    margin: 0;
    font-size: 14px;
  }

  .kind {
    font-size: 12px;
    color: #6b7280;
  }

  .marginal {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .marginal li {
    display: grid;
    grid-template-columns: minmax(120px, 210px) 1fr 52px;
    align-items: center;
    gap: 10px;
    font-size: 12px;
  }

  .value-name {
    color: #374151;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bar-track {
    height: 14px;
    background: #f3f4f6;
    border-radius: 3px;
    overflow: hidden;
  }

  .bar-fill {
    display: block;
    height: 100%;
    border-radius: 0 4px 4px 0;
  }

  .value-share {
    text-align: right;
    color: #111827;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }

  .numeric-rows {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .numeric-rows li {
    display: grid;
    grid-template-columns: minmax(120px, 210px) 1fr 60px 62px;
    align-items: center;
    gap: 10px;
    font-size: 12px;
  }

  .plot {
    position: relative;
    display: block;
    height: 16px;
    background: #f3f4f6;
    border-radius: 3px;
  }

  .spread {
    position: absolute;
    top: 5px;
    height: 6px;
    min-width: 2px;
    background: #9ec5f4;
    border-radius: 3px;
  }

  .dot {
    position: absolute;
    top: 3px;
    width: 10px;
    height: 10px;
    margin-left: -5px;
    border-radius: 50%;
    background: #2a78d6;
    border: 2px solid #ffffff;
  }

  .row-count {
    text-align: right;
    color: #9ca3af;
    font-variant-numeric: tabular-nums;
  }

  .axis-note {
    color: #9ca3af;
  }

  .histogram {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 110px;
    padding: 4px;
    background: #f9fafb;
    border-radius: 6px;
  }

  .bin {
    flex: 1;
    min-height: 1px;
    background: #2a78d6;
    border-radius: 3px 3px 0 0;
  }

  .stats {
    margin: 0;
    font-size: 12px;
    color: #6b7280;
    font-variant-numeric: tabular-nums;
  }

  .toggle {
    align-self: flex-start;
    border: 1px solid #e5e7eb;
    background: #ffffff;
    color: #2563eb;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }

  .toggle:hover {
    background: #f8fafc;
  }

  .breakdown-scroll {
    overflow: auto;
    max-height: 360px;
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
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    padding: 8px;
    text-align: left;
    font-weight: 600;
    color: #374151;
    white-space: nowrap;
  }

  .value-head {
    text-align: center;
  }

  .swatch {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 2px;
    margin-right: 4px;
  }

  tbody th {
    padding: 6px 8px;
    text-align: left;
    font-weight: 600;
    color: #111827;
    border-bottom: 1px solid #f3f4f6;
    white-space: nowrap;
  }

  tbody td {
    border-bottom: 1px solid #f3f4f6;
    padding: 6px 8px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }

  .count {
    text-align: right;
    color: #6b7280;
  }

  /* 2px surface gap between heatmap fills, as in the lookup table. */
  .cell {
    border-left: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    font-weight: 600;
  }
</style>
