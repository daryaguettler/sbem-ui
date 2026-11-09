<script lang="ts">
  /**
   * Choosing what a prior is conditioned on.
   *
   * Any combination of semantic fields and raw GIS columns is allowed -- they all
   * become one compound key -- so the job here is to make the cost of each choice
   * visible before it is made: how many distinct values a field has, how much of
   * the stock it covers, and how many lookup-table rows the current combination
   * would produce.
   */
  import type { ConditioningCandidate, ConditionPreview } from '../../types/priorTrees';
  import { formatPercent } from '../../utils/priorViz';
  import Icon from '../Icon.svelte';

  export let candidates: ConditioningCandidate[] = [];
  export let selected: string[] = [];
  export let preview: ConditionPreview | null = null;
  export let rowCount = 0;
  export let onToggle: (name: string) => void;
  export let onReorder: (names: string[]) => void;

  const SOURCE_LABELS: Record<string, string> = {
    semantic: 'Characteristic from your data',
    gis: 'GIS column',
    sampled: 'Estimated characteristic',
  };

  /** Conditioning fields are grouped by where their values come from. */
  $: groups = (['semantic', 'gis', 'sampled'] as const)
    .map((source) => ({
      source,
      label: SOURCE_LABELS[source],
      items: candidates.filter((candidate) => candidate.source === source),
    }))
    .filter((group) => group.items.length > 0);

  function move(index: number, delta: number) {
    const next = [...selected];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onReorder(next);
  }

  function describe(candidate: ConditioningCandidate): string {
    if (candidate.source === 'sampled') return 'estimated, no observed values';
    if (candidate.dtype === 'numeric') return 'numeric: group it into ranges as a characteristic first';
    return `${candidate.cardinality} values · ${formatPercent(candidate.coverage)} of rows`;
  }
</script>

<div class="picker">
  {#if selected.length > 0}
    <div class="selection">
      <span class="selection-label">Depends on</span>
      <ol class="chosen">
        {#each selected as name, index}
          <li>
            <span class="chip-name">{name}</span>
            <span class="chip-actions">
              <button
                type="button"
                class="btn btn-ghost btn-sm"
                title="Move earlier"
                aria-label="Move {name} earlier"
                disabled={index === 0}
                onclick={() => move(index, -1)}
              ><Icon name="arrow-up" size={14} /></button>
              <button
                type="button"
                class="btn btn-ghost btn-sm"
                title="Move later"
                aria-label="Move {name} later"
                disabled={index === selected.length - 1}
                onclick={() => move(index, 1)}
              ><Icon name="arrow-down" size={14} /></button>
              <button
                type="button"
                class="btn btn-ghost btn-sm"
                title="Remove"
                aria-label="Remove {name}"
                onclick={() => onToggle(name)}
              ><Icon name="x" size={14} /></button>
            </span>
          </li>
        {/each}
      </ol>
    </div>

    {#if preview}
      <p class="preview" class:thin={preview.coverage < 0.9}>
        <strong>{preview.keyCount}</strong>
        {preview.keyCount === 1 ? 'combination' : 'combinations'} occur in your data, covering
        <strong>{formatPercent(preview.coverage)}</strong> of {preview.rowCount.toLocaleString()} buildings.
        {#if preview.coverage < 1}
          The rest use “Everything else”.
        {/if}
      </p>
    {/if}
  {:else}
    <p class="preview">
      Nothing selected: one distribution for every building. Pick fields to vary it by.
    </p>
  {/if}

  {#each groups as group}
    <div class="group">
      <h4>{group.label}</h4>
      <div class="options">
        {#each group.items as candidate}
          <button
            type="button"
            class="option"
            class:active={selected.includes(candidate.name)}
            class:disabled={!candidate.conditionable}
            disabled={!candidate.conditionable}
            title={candidate.description || candidate.name}
            onclick={() => onToggle(candidate.name)}
          >
            <span class="option-name">
              {candidate.name}
              {#if candidate.highCardinality}
                <span class="warn-mark" title="Very high cardinality — this makes a huge table">
                  <Icon name="alert" size={14} label="Very high cardinality" />
                </span>
              {/if}
            </span>
            <span class="option-meta">{describe(candidate)}</span>
          </button>
        {/each}
      </div>
    </div>
  {/each}

  {#if rowCount === 0}
    <p class="callout callout-warn">
      No GIS rows are loaded, so combinations can't be counted. Upload and validate GIS data to
      generate a table that matches your actual stock.
    </p>
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .selection {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .selection-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-2);
  }

  .chosen {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chosen li {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    padding: 0 var(--space-1) 0 var(--space-3);
    border: 1px solid var(--accent-border);
    border-radius: var(--radius);
    background: var(--accent-soft);
    font-size: var(--text-sm);
  }

  .chip-name {
    font-weight: 600;
    color: var(--accent-hover);
  }

  .chip-actions {
    display: flex;
  }

  .chip-actions .btn {
    padding: 0 var(--space-1);
  }

  .preview {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-2);
  }

  .preview.thin {
    color: var(--warn-text);
  }

  .group h4 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  .options {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-2);
  }

  .option {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    text-align: left;
    cursor: pointer;
  }

  .option:hover:not(.disabled) {
    border-color: var(--accent-border);
    background: var(--surface-2);
  }

  .option.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .option.disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .option-name {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text);
  }

  .warn-mark {
    display: inline-flex;
    color: var(--warn-text);
  }

  .option-meta {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
</style>
