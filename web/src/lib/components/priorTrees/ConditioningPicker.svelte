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

  export let candidates: ConditioningCandidate[] = [];
  export let selected: string[] = [];
  export let preview: ConditionPreview | null = null;
  export let rowCount = 0;
  export let onToggle: (name: string) => void;
  export let onReorder: (names: string[]) => void;

  const SOURCE_LABELS: Record<string, string> = {
    semantic: 'Semantic field',
    gis: 'GIS column',
    sampled: 'Sampled field',
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
    if (candidate.source === 'sampled') return 'sampled, no observed values';
    if (candidate.dtype === 'numeric') return 'numeric — bucket it into a semantic field first';
    return `${candidate.cardinality} values · ${formatPercent(candidate.coverage)} of rows`;
  }
</script>

<div class="picker">
  {#if selected.length > 0}
    <div class="selection">
      <span class="selection-label">Conditioned on</span>
      <ol class="chosen">
        {#each selected as name, index}
          <li>
            <span class="chip-name">{name}</span>
            <span class="chip-actions">
              <button type="button" title="Move earlier" disabled={index === 0} onclick={() => move(index, -1)}>↑</button>
              <button
                type="button"
                title="Move later"
                disabled={index === selected.length - 1}
                onclick={() => move(index, 1)}
              >↓</button>
              <button type="button" title="Remove" class="remove" onclick={() => onToggle(name)}>×</button>
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
          The rest use the fallback.
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
                <span class="warn-dot" title="Very high cardinality — this makes a huge table">!</span>
              {/if}
            </span>
            <span class="option-meta">{describe(candidate)}</span>
          </button>
        {/each}
      </div>
    </div>
  {/each}

  {#if rowCount === 0}
    <p class="hint">
      No GIS rows are loaded, so combinations can't be counted. Upload and validate GIS data to
      generate a table that matches your actual stock.
    </p>
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .selection {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .selection-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-2);
  }

  .chosen {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chosen li {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px 4px 10px;
    border: 1px solid var(--accent-border);
    border-radius: 999px;
    background: var(--accent-soft);
    font-size: 13px;
  }

  .chip-name {
    font-weight: 600;
    color: var(--accent-hover);
  }

  .chip-actions {
    display: flex;
    gap: 2px;
  }

  .chip-actions button {
    border: none;
    background: transparent;
    color: var(--accent-hover);
    font-size: 12px;
    line-height: 1;
    padding: 2px 3px;
    cursor: pointer;
    border-radius: 4px;
  }

  .chip-actions button:disabled {
    color: var(--accent-border);
    cursor: default;
  }

  .chip-actions button:not(:disabled):hover {
    background: var(--accent-soft);
  }

  .chip-actions .remove {
    color: var(--err-text);
  }

  .preview {
    margin: 0;
    font-size: 13px;
    color: var(--text-2);
    line-height: 1.5;
  }

  .preview.thin {
    color: var(--warn-text);
  }

  .group h4 {
    margin: 0 0 8px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted);
  }

  .options {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 8px;
  }

  .option {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    text-align: left;
    cursor: pointer;
    font-weight: 400;
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
    opacity: 0.55;
    cursor: not-allowed;
  }

  .option-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .warn-dot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--warn-bg);
    color: var(--warn-text);
    font-size: 10px;
    font-weight: 700;
  }

  .option-meta {
    font-size: 11px;
    color: var(--text-muted);
  }

  .hint {
    margin: 0;
    font-size: 13px;
    color: var(--warn-text);
    background: var(--warn-bg);
    border: 1px solid var(--warn-border);
    border-radius: 8px;
    padding: 10px 12px;
  }
</style>
