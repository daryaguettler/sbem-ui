<script lang="ts">
  /** "Paste from a spreadsheet": odds copied as cells, read by utils/pasteOdds and handed to the editor. */
  import { parsePastedOdds, type PastedRow } from '../../utils/pasteOdds';

  let {
    values,
    keys = [],
    separator = '.',
    onApply,
  }: {
    values: string[];
    /** The table's combinations; empty for odds that are the same for every building. */
    keys?: string[];
    separator?: string;
    onApply: (rows: PastedRow[]) => void;
  } = $props();

  let open = $state(false);
  let text = $state('');
  let message = $state<string | null>(null);
  let warnings = $state<string[]>([]);

  const example = $derived(
    keys.length
      ? `${keys[0].split(separator).join(' · ')}\t${values.map((_, i) => (i === 0 ? '60%' : '20%')).join('\t')}`
      : values.map((value, i) => `${value}\t${i === 0 ? '60%' : '20%'}`).join('\n')
  );

  function apply() {
    const parsed = parsePastedOdds(text, values, keys, separator);
    warnings = parsed.warnings;
    if (parsed.rows.length) {
      onApply(parsed.rows);
      message = `Updated ${parsed.rows.length} ${parsed.rows.length === 1 ? 'row' : 'rows'}.`;
      text = '';
    } else {
      message = null;
    }
  }
</script>

{#if !open}
  <button type="button" class="btn btn-secondary btn-sm" onclick={() => (open = true)}>Paste from a spreadsheet</button>
{:else}
  <div class="paste">
    <label class="field">
      <span>Paste cells copied from a spreadsheet</span>
      <span class="field-hint">
        {keys.length
          ? `One row per combination, named in the first column; a header row with the values (${values.join(', ')}) sets the column order. "Everything else" sets the fallback.`
          : `A row of shares in the order ${values.join(', ')}, or two columns: value and share.`}
        Decimals or percentages; each row is rescaled to add up to 100%.
      </span>
      <textarea rows="5" bind:value={text} placeholder={example}></textarea>
    </label>
    <div class="actions">
      <button type="button" class="btn btn-sm" onclick={apply} disabled={!text.trim()}>Apply</button>
      <button type="button" class="btn btn-ghost btn-sm" onclick={() => ((open = false), (message = null), (warnings = []))}>Close</button>
    </div>
    {#if message}<p class="status-ok">{message}</p>{/if}
    {#each warnings as warning}<p class="hint">{warning}</p>{/each}
  </div>
{/if}

<style>
  .paste {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  textarea {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }

  .status-ok {
    font-size: var(--text-sm);
  }
</style>
