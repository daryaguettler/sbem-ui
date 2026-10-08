<script lang="ts">
  /**
   * What each scenario does to the stock.
   *
   * Baseline and scenario are sampled from the same draw, so every difference
   * shown is the scenario's doing rather than two samples disagreeing. Each value
   * gets a paired bar -- baseline above, scenario below, one shared scale -- plus
   * the change in percentage points, which is the number people actually quote.
   */
  import type { ScenarioPreview } from '../../types/priorTrees';
  import { seriesColor } from '../../utils/priorViz';

  export let preview: ScenarioPreview;

  const BASELINE_COLOR = seriesColor(0);
  const SCENARIO_COLOR = seriesColor(1);

  function points(baseline: number, scenario: number): string {
    const delta = (scenario - baseline) * 100;
    if (Math.abs(delta) < 0.05) return '—';
    return `${delta > 0 ? '+' : '−'}${Math.abs(delta).toFixed(1)} pp`;
  }

  function percent(value: number): string {
    return `${(value * 100).toFixed(1)}%`;
  }
</script>

<div class="scenario-preview">
  <p class="context">
    {preview.n.toLocaleString()} buildings sampled
    {#if preview.contextSource === 'gis'}
      over your stock, drawing {preview.contextFields.join(', ')} from
      {preview.contextRowCount.toLocaleString()} GIS rows.
    {:else}
      (no conditioning fields, so no GIS context was needed).
    {/if}
    Every scenario is applied to that same baseline. Seed {preview.seed ?? 'random'}.
  </p>

  <ul class="legend">
    <li><span class="swatch" style="background: {BASELINE_COLOR};"></span> Baseline</li>
    <li><span class="swatch" style="background: {SCENARIO_COLOR};"></span> Scenario</li>
  </ul>

  {#each preview.scenarios as scenario}
    <section class="scenario">
      <header>
        <h4>{scenario.name}</h4>
        <span class="meta">
          changes {scenario.changed.join(', ') || 'nothing'}
          {#if scenario.downstream.length > 0}
            · resamples {scenario.downstream.join(', ')}
          {/if}
        </span>
      </header>

      {#if scenario.features.length === 0}
        <p class="empty">This scenario doesn't change any sampled feature.</p>
      {/if}

      {#each scenario.features as feature}
        <div class="feature">
          <h5>
            {feature.feature}
            {#if scenario.downstream.includes(feature.feature)}
              <span class="tag">downstream</span>
            {/if}
          </h5>

          {#if feature.dtype === 'numeric' && feature.numeric}
            {@const numeric = feature.numeric}
            <p class="numeric-line">
              mean <strong>{numeric.baselineMean.toFixed(3)}</strong>
              → <strong>{numeric.scenarioMean.toFixed(3)}</strong>
              <span class="delta" class:up={numeric.scenarioMean > numeric.baselineMean}>
                ({numeric.scenarioMean > numeric.baselineMean ? '+' : '−'}{Math.abs(
                  numeric.scenarioMean - numeric.baselineMean
                ).toFixed(3)})
              </span>
              · sd {numeric.baselineStd.toFixed(3)} → {numeric.scenarioStd.toFixed(3)}
            </p>
          {:else}
            <ul class="rows">
              {#each feature.shares as share}
                <li>
                  <span class="value-name" title={share.value}>{share.value}</span>
                  <span class="pair">
                    <span class="bar" style="width: {share.baseline * 100}%; background: {BASELINE_COLOR};"
                    ><span class="bar-label" class:inside={share.baseline > 0.72}
                    >{percent(share.baseline)}</span></span>
                    <span class="bar" style="width: {share.scenario * 100}%; background: {SCENARIO_COLOR};"
                    ><span class="bar-label" class:inside={share.scenario > 0.72}
                    >{percent(share.scenario)}</span></span>
                  </span>
                  <span
                    class="delta"
                    class:up={share.scenario > share.baseline}
                    class:down={share.scenario < share.baseline}
                  >{points(share.baseline, share.scenario)}</span>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/each}
    </section>
  {/each}
</div>

<style>
  .scenario-preview {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .context {
    margin: 0;
    font-size: 13px;
    color: #4b5563;
    line-height: 1.5;
  }

  .legend {
    display: flex;
    gap: 16px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 12px;
    color: #374151;
  }

  .legend li {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }

  .scenario {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-top: 16px;
    border-top: 1px solid #f3f4f6;
  }

  .scenario header {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }

  .scenario h4 {
    margin: 0;
    font-size: 14px;
  }

  .meta {
    font-size: 12px;
    color: #6b7280;
  }

  .feature h5 {
    margin: 0 0 6px;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .tag {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #5b21b6;
    background: #ede9fe;
    border-radius: 999px;
    padding: 2px 7px;
  }

  .rows {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .rows li {
    display: grid;
    grid-template-columns: minmax(110px, 200px) 1fr 74px;
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

  /* Two thin bars on one scale: the comparison is the vertical pair. */
  .pair {
    display: flex;
    flex-direction: column;
    gap: 2px;
    background: #f9fafb;
    border-radius: 3px;
    padding: 2px;
  }

  .bar {
    height: 11px;
    min-width: 2px;
    border-radius: 0 3px 3px 0;
    position: relative;
  }

  .bar-label {
    position: absolute;
    left: calc(100% + 6px);
    top: -1px;
    font-size: 10px;
    color: #6b7280;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .bar-label.inside {
    left: auto;
    right: 5px;
    color: #ffffff;
    font-weight: 600;
  }

  .delta {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: #6b7280;
  }

  .delta.up {
    color: #166534;
  }

  .delta.down {
    color: #b91c1c;
  }

  .numeric-line {
    margin: 0;
    font-size: 12px;
    color: #374151;
    font-variant-numeric: tabular-nums;
  }

  .empty {
    margin: 0;
    font-size: 12px;
    color: #9ca3af;
  }
</style>
