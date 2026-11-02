<script lang="ts">
  import { untrack } from 'svelte';
  import { checkComponentExistence } from '../../api/componentLibrary';
  import { buildSelectorCombinations, type SelectorCombination } from '../../utils/componentMapTree';

  let {
    componentType,
    sourceFields,
    semanticFields,
    suffix,
    onOpenRecord,
  }: {
    componentType: string;
    sourceFields: string[];
    semanticFields: Array<{ name: string; options?: string[] }>;
    suffix?: string;
    /** The record form opens in the surrounding side panel, not over the page. */
    onOpenRecord: (name: string, exists: boolean) => void;
  } = $props();

  let combinations = $state<SelectorCombination[]>([]);
  let existence = $state<Record<string, boolean>>({});
  let loading = $state(false);
  let error = $state<string | null>(null);

  async function refresh() {
    combinations = buildSelectorCombinations(sourceFields, semanticFields, suffix);
    if (combinations.length === 0) {
      existence = {};
      return;
    }
    loading = true;
    error = null;
    try {
      existence = await checkComponentExistence(
        componentType,
        combinations.map((c) => c.name)
      );
    } catch (err) {
      // Backend unreachable (e.g. mid-restart) or a real API error -- don't
      // crash the reactive effect, just show unknown-existence rows with a
      // retry affordance instead of an uncaught rejection per re-render.
      error = err instanceof Error ? err.message : 'Failed to check which records already exist.';
      existence = {};
    } finally {
      loading = false;
    }
  }

  // Re-check when the inputs change. refresh() itself reads and writes this
  // component's state (combinations, loading, ...), so it runs untracked; otherwise
  // the effect re-triggers itself forever (effect_update_depth_exceeded) and the page
  // freezes as soon as a field is ticked.
  $effect(() => {
    componentType;
    sourceFields;
    semanticFields;
    suffix;
    untrack(refresh);
  });

  const coveredCount = $derived(combinations.filter((c) => existence[c.name]).length);
</script>

<div class="coverage">
  <div class="coverage-header">
    <strong>{coveredCount} of {combinations.length} {componentType} records exist</strong>
    {#if loading}<span class="hint">checking…</span>{/if}
  </div>

  {#if error}
    <p class="error" role="alert">
      {error}
      <button type="button" class="btn btn-danger btn-sm" onclick={refresh}>Retry</button>
    </p>
  {/if}

  {#if combinations.length === 0}
    <p class="hint">Tick at least one characteristic to see which records this part needs.</p>
  {:else}
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            {#each sourceFields as field}
              <th>{field}</th>
            {/each}
            <th>Record name</th>
            <th>Status</th>
            <th><span class="visually-hidden">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {#each combinations as combo}
            {@const exists = Boolean(existence[combo.name])}
            <tr>
              {#each sourceFields as field}
                <td>{combo.values[field]}</td>
              {/each}
              <td class="record-name">{combo.name}</td>
              <td>
                {#if loading}
                  <span class="hint">…</span>
                {:else if exists}
                  <span class="state ok"><span aria-hidden="true">✓</span> Exists</span>
                {:else}
                  <span class="state missing"><span aria-hidden="true">✕</span> Missing</span>
                {/if}
              </td>
              <td class="row-action">
                <button
                  type="button"
                  class={exists ? 'btn btn-secondary btn-sm' : 'btn btn-sm'}
                  onclick={() => onOpenRecord(combo.name, exists)}
                >
                  {exists ? 'Edit' : '+ Create'}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .coverage {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
    background: var(--surface-2);
  }

  .coverage-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
    color: var(--text);
  }

  .hint {
    font-size: 12px;
    color: var(--text-muted);
  }

  .error {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 8px;
    font-size: 12px;
    color: var(--err-text);
  }

  .table-scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  th {
    text-align: left;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    color: var(--text-muted);
    font-weight: 600;
    white-space: nowrap;
  }

  td {
    padding: 6px 8px;
    border-bottom: 1px solid var(--surface-3);
    color: var(--text);
  }

  .record-name {
    font-family: var(--font-mono);
    font-size: 11px;
    overflow-wrap: anywhere;
  }

  .state {
    font-weight: 600;
    white-space: nowrap;
  }

  .state.ok {
    color: var(--ok-text);
  }

  .state.missing {
    color: var(--err-text);
  }

  .row-action {
    text-align: right;
  }
</style>
