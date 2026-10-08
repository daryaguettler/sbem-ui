<script lang="ts">
  import SchemaForm from '../componentLibrary/SchemaForm.svelte';
  import { checkComponentExistence } from '../../api/componentLibrary';
  import { buildSelectorCombinations, type SelectorCombination } from '../../utils/componentMapTree';

  let {
    componentType,
    sourceFields,
    semanticFields,
    suffix,
  }: {
    componentType: string;
    sourceFields: string[];
    semanticFields: Array<{ name: string; options?: string[] }>;
    suffix?: string;
  } = $props();

  let combinations = $state<SelectorCombination[]>([]);
  let existence = $state<Record<string, boolean>>({});
  let loading = $state(false);
  let error = $state<string | null>(null);

  type PanelState = { open: false } | { open: true; name: string; exists: boolean };
  let panel = $state<PanelState>({ open: false });

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

  $effect(() => {
    componentType;
    sourceFields;
    semanticFields;
    suffix;
    refresh();
  });

  const coveredCount = $derived(combinations.filter((c) => existence[c.name]).length);

  function openRecord(name: string) {
    panel = { open: true, name, exists: Boolean(existence[name]) };
  }

  function onSaved() {
    panel = { open: false };
    refresh();
  }
</script>

<div class="coverage">
  <div class="coverage-header">
    <strong>{coveredCount} / {combinations.length} {componentType} records exist</strong>
    {#if loading}<span class="hint">checking...</span>{/if}
  </div>

  {#if error}
    <p class="error">
      {error}
      <button type="button" class="retry" onclick={refresh}>Retry</button>
    </p>
  {/if}

  {#if combinations.length === 0}
    <p class="hint">Choose at least one semantic field above to see the records this selector needs.</p>
  {:else}
    <table>
      <thead>
        <tr>
          {#each sourceFields as field}
            <th>{field}</th>
          {/each}
          <th>{componentType} record</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each combinations as combo}
          <tr>
            {#each sourceFields as field}
              <td>{combo.values[field]}</td>
            {/each}
            <td class="record-name">{combo.name}</td>
            <td>
              {#if existence[combo.name]}
                <button type="button" class="status ok" onclick={() => openRecord(combo.name)}>Edit</button>
              {:else}
                <button type="button" class="status missing" onclick={() => openRecord(combo.name)}>
                  + Create
                </button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<svelte:window
  onkeydown={(event) => panel.open && event.key === 'Escape' && (panel = { open: false })}
/>

{#if panel.open}
  <div class="panel-overlay">
    <button type="button" class="panel-overlay-backdrop" aria-label="Close" onclick={() => (panel = { open: false })}
    ></button>
    <div class="panel" role="dialog" aria-modal="true">
      <h3>{panel.exists ? 'Edit' : 'Create'} {componentType}: {panel.name}</h3>
      <SchemaForm
        {componentType}
        mode={panel.exists ? 'edit' : 'create'}
        name={panel.exists ? panel.name : null}
        presetName={panel.name}
        onSaved={onSaved}
        onCancel={() => (panel = { open: false })}
      />
    </div>
  </div>
{/if}

<style>
  .coverage {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px;
    background: #f9fafb;
  }

  .coverage-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
    color: #111827;
  }

  .hint {
    font-size: 12px;
    color: #6b7280;
  }

  .error {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 8px;
    font-size: 12px;
    color: #b91c1c;
  }

  .retry {
    border: 1px solid #fecaca;
    border-radius: 6px;
    background: #ffffff;
    color: #b91c1c;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  th {
    text-align: left;
    padding: 6px 8px;
    border-bottom: 1px solid #e5e7eb;
    color: #6b7280;
    font-weight: 600;
  }

  td {
    padding: 6px 8px;
    border-bottom: 1px solid #f3f4f6;
    color: #111827;
  }

  .record-name {
    font-family: monospace;
    font-size: 11px;
  }

  .status {
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }

  .status.ok {
    background: #dcfce7;
    color: #15803d;
  }

  .status.missing {
    background: #fee2e2;
    color: #b91c1c;
  }

  .panel-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
  }

  .panel-overlay-backdrop {
    position: absolute;
    inset: 0;
    border: none;
    padding: 0;
    background: rgba(15, 23, 42, 0.4);
    cursor: default;
  }

  .panel {
    position: relative;
    background: #ffffff;
    border-radius: 12px;
    padding: 20px;
    width: 480px;
    max-height: 80vh;
    overflow: auto;
  }

  .panel h3 {
    margin: 0 0 12px;
    font-size: 15px;
    color: #111827;
  }
</style>
