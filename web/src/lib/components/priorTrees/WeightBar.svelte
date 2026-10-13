<script lang="ts">
  /**
   * One distribution as a 100% stacked bar. Segments carry a 2px surface gap so
   * adjacent hues never touch, and every segment wide enough to hold text is
   * labelled directly -- identity is never left to color alone.
   */
  import type { Distribution } from '../../types/priorTrees';
  import { distributionTotal, formatShare, toSegments } from '../../utils/priorViz';

  export let distribution: Distribution;
  export let order: string[] = [];
  export let showLegend = true;

  $: total = distributionTotal(distribution);
  $: segments = toSegments(distribution, order)
    .map((segment) => ({ ...segment, share: total > 0 ? segment.weight / total : 0 }))
    .filter((segment) => segment.share > 0);
</script>

<div class="weight-bar">
  <div class="track" role="img" aria-label={segments.map((s) => `${s.value} ${formatShare(s.share)}`).join(', ')}>
    {#each segments as segment}
      <div
        class="segment"
        style="width: {segment.share * 100}%; background: {segment.color};"
        title="{segment.value}: {formatShare(segment.share)}"
      >
        {#if segment.share >= 0.14}
          <span class="inline-label">{formatShare(segment.share)}</span>
        {/if}
      </div>
    {/each}
    {#if segments.length === 0}
      <div class="empty">No weight assigned</div>
    {/if}
  </div>

  {#if showLegend && segments.length > 0}
    <ul class="legend">
      {#each segments as segment}
        <li>
          <span class="swatch" style="background: {segment.color};"></span>
          <span class="name">{segment.value}</span>
          <span class="share">{formatShare(segment.share)}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .weight-bar {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .track {
    display: flex;
    height: 20px;
    border-radius: 4px;
    overflow: hidden;
    background: var(--surface-3);
  }

  /* The gap is a surface-colored border, so segments read as separate marks. */
  .segment + .segment {
    border-left: 2px solid var(--surface);
  }

  .segment {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 2px;
    overflow: hidden;
  }

  .inline-label {
    font-size: 11px;
    font-weight: 600;
    /* fixed white + shadow: legible on every series step in both themes */
    color: #ffffff;
    text-shadow: 0 0 2px rgba(0, 0, 0, 0.55);
    white-space: nowrap;
  }

  .empty {
    padding: 0 8px;
    font-size: 12px;
    color: var(--text-faint);
    line-height: 20px;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .legend li {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .name {
    color: var(--text-2);
  }

  .share {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
</style>
