<script lang="ts">
  /**
   * One distribution as a 100% stacked bar. Segments carry a 2px surface gap so
   * adjacent hues never touch, and every segment wide enough to hold text is
   * labelled directly -- identity is never left to color alone.
   */
  import type { Distribution } from '../../types/priorTrees';
  import { distributionTotal, formatShare, moveBoundary, toSegments } from '../../utils/priorViz';

  export let distribution: Distribution;
  export let order: string[] = [];
  export let showLegend = true;
  /** Given, the bar is editable: drag (or arrow-key) a boundary to move weight between its two neighbours. */
  export let onChange: ((distribution: Distribution) => void) | null = null;

  let track: HTMLDivElement;
  $: editOrder = order.length ? order : Object.keys(distribution);
  $: shares = editOrder.map((value) =>
    total > 0 ? (Number(distribution[value]) || 0) / total : 1 / Math.max(editOrder.length, 1)
  );
  $: cuts = shares.slice(0, -1).map((_, i) => shares.slice(0, i + 1).reduce((sum, s) => sum + s, 0));

  function emit(next: number[]) {
    onChange?.(Object.fromEntries(editOrder.map((value, i) => [value, Number(next[i].toFixed(4))])));
  }

  function drag(index: number, event: PointerEvent) {
    const handle = event.currentTarget as HTMLElement;
    handle.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => {
      const rect = track.getBoundingClientRect();
      emit(moveBoundary(shares, index, (e.clientX - rect.left) / rect.width));
    };
    const stop = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', stop);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
  }

  function nudge(index: number, event: KeyboardEvent) {
    const step = event.shiftKey ? 0.05 : 0.01;
    const delta = event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -step : event.key === 'ArrowRight' || event.key === 'ArrowUp' ? step : 0;
    if (!delta) return;
    event.preventDefault();
    emit(moveBoundary(shares, index, cuts[index] + delta));
  }

  $: total = distributionTotal(distribution);
  $: segments = toSegments(distribution, order)
    .map((segment) => ({ ...segment, share: total > 0 ? segment.weight / total : 0 }))
    .filter((segment) => segment.share > 0);
</script>

<div class="weight-bar">
  <div class="track-wrap">
  <div class="track" bind:this={track} role="img" aria-label={segments.map((s) => `${s.value} ${formatShare(s.share)}`).join(', ')}>
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
  {#if onChange}
    {#each cuts as cut, i}
      <span
        class="handle"
        role="slider"
        tabindex="0"
        style="left: {cut * 100}%;"
        aria-label="Boundary between {editOrder[i]} and {editOrder[i + 1]}"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={Math.round(cut * 100)}
        aria-valuetext="{editOrder[i]} {formatShare(shares[i])}, {editOrder[i + 1]} {formatShare(shares[i + 1])}"
        title="Drag to move weight between {editOrder[i]} and {editOrder[i + 1]}"
        onpointerdown={(event) => drag(i, event)}
        onkeydown={(event) => nudge(i, event)}
      ></span>
    {/each}
  {/if}
  </div>
  {#if onChange}<p class="drag-hint">Drag a boundary (or focus it and use the arrow keys) to move weight between neighbours.</p>{/if}

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
    gap: var(--space-2);
  }

  .track-wrap {
    position: relative;
  }

  .handle {
    position: absolute;
    top: -3px;
    width: 10px;
    height: 26px;
    transform: translateX(-50%);
    border: 2px solid var(--text-2);
    border-radius: var(--radius-sm);
    background: var(--surface);
    cursor: ew-resize;
    touch-action: none;
  }

  .handle:hover,
  .handle:focus-visible {
    border-color: var(--accent);
    outline: none;
    box-shadow: 0 0 0 3px var(--focus-ring);
  }

  .drag-hint {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .track {
    display: flex;
    height: 20px;
    border-radius: var(--radius-sm);
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
    font-size: var(--text-2xs);
    font-weight: 600;
    color: #ffffff; /* raw-ok: fixed white + shadow, legible on every series step in both themes */
    text-shadow: 0 0 2px rgba(0, 0, 0, 0.55);
    white-space: nowrap;
  }

  .empty {
    padding: 0 var(--space-2);
    line-height: 20px;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .legend li {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-sm);
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
