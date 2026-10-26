<script lang="ts">
  import SchemaForm from '../components/componentLibrary/SchemaForm.svelte';
  import SidePanel from '../components/SidePanel.svelte';
  import {
    fetchComponentTypes,
    fetchComponentRecords,
    deleteComponentRecord,
    type ComponentRecord,
  } from '../api/componentLibrary';
  import Explain from '../components/Explain.svelte';
  import { HELP } from '../help';
  const help = HELP.componentLibrary;

  let types = $state<string[]>([]);
  let selectedType = $state<string | null>(null);
  let records = $state<ComponentRecord[]>([]);
  let loadingTypes = $state(true);
  let loadingRecords = $state(false);
  let error = $state<string | null>(null);

  type PanelState = { mode: 'closed' } | { mode: 'create' } | { mode: 'edit'; name: string };
  let panel = $state<PanelState>({ mode: 'closed' });

  async function loadTypes() {
    loadingTypes = true;
    try {
      const { types: fetched } = await fetchComponentTypes();
      types = fetched;
      if (!selectedType && fetched.length > 0) {
        selectType(fetched[0]);
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load component types.';
    } finally {
      loadingTypes = false;
    }
  }

  async function loadRecords() {
    if (!selectedType) return;
    loadingRecords = true;
    error = null;
    try {
      records = await fetchComponentRecords(selectedType);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load records.';
    } finally {
      loadingRecords = false;
    }
  }

  function selectType(type: string) {
    selectedType = type;
    panel = { mode: 'closed' };
    loadRecords();
  }

  function openCreate() {
    panel = { mode: 'create' };
  }

  function openEdit(name: string) {
    panel = { mode: 'edit', name };
  }

  function closePanel() {
    panel = { mode: 'closed' };
  }

  function onSaved() {
    panel = { mode: 'closed' };
    loadRecords();
  }

  async function removeRecord(name: string) {
    if (!selectedType) return;
    if (!confirm(`Delete ${selectedType} record "${name}"? This cannot be undone.`)) return;
    try {
      await deleteComponentRecord(selectedType, name);
      await loadRecords();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to delete record.';
    }
  }

  loadTypes();
</script>

<div class="workflow">
  <header class="workflow-header">
    <h1>Component Library <Explain text={help.page} tip /></h1>
    <Explain text={help.page} />
  </header>

  <div class="body" class:panel-open={panel.mode !== 'closed'}>
    <nav class="types" aria-label="Component types">
      {#if loadingTypes}
        <p class="hint">Loading types…</p>
      {:else}
        {#each types as type}
          <button
            type="button"
            class="type-item"
            class:active={type === selectedType}
            aria-current={type === selectedType ? 'true' : undefined}
            onclick={() => selectType(type)}
          >
            {type}
          </button>
        {/each}
      {/if}
    </nav>

    <section class="records">
      {#if selectedType}
        <div class="records-header">
          <h2>{selectedType} <Explain text={help.records} tip /></h2>
          <button type="button" class="btn" onclick={openCreate}>+ Add {selectedType}</button>
        </div>
        <Explain text={help.records} />

        {#if error}
          <p class="error" role="alert">{error}</p>
        {/if}

        {#if loadingRecords}
          <p class="hint">Loading records…</p>
        {:else if records.length === 0}
          <div class="empty">
            <p>No {selectedType} records yet.</p>
            <button type="button" class="btn btn-secondary" onclick={openCreate}>+ Add the first one</button>
          </div>
        {:else}
          <table>
            <thead>
              <tr><th>Name</th><th><span class="visually-hidden">Actions</span></th></tr>
            </thead>
            <tbody>
              {#each records as record}
                <tr class:editing={panel.mode === 'edit' && panel.name === record.Name}>
                  <td>{record.Name}</td>
                  <td class="row-actions">
                    <button type="button" class="btn btn-secondary btn-sm" onclick={() => openEdit(record.Name)}>Edit</button>
                    <button type="button" class="btn btn-danger btn-sm" onclick={() => removeRecord(record.Name)}>Delete</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      {:else}
        <p class="hint">Select a component type.</p>
      {/if}
    </section>

    {#if panel.mode !== 'closed' && selectedType}
      <div class="editor-slot">
        <SidePanel
          title={panel.mode === 'create' ? `New ${selectedType}` : `Edit ${panel.mode === 'edit' ? panel.name : ''}`}
          subtitle={selectedType}
          onClose={closePanel}
        >
          {#key `${panel.mode}:${panel.mode === 'edit' ? panel.name : ''}`}
            <SchemaForm
              componentType={selectedType}
              mode={panel.mode === 'create' ? 'create' : 'edit'}
              name={panel.mode === 'edit' ? panel.name : null}
              onSaved={onSaved}
              onCancel={closePanel}
            />
          {/key}
        </SidePanel>
      </div>
    {/if}
  </div>
</div>

<style>
  .body {
    position: relative;
    flex: 1;
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    min-height: 0;
    overflow: hidden;
  }

  /* The editor docks as a third column; records stay visible beside it. */
  .body.panel-open {
    grid-template-columns: 220px minmax(0, 1fr) minmax(400px, 560px);
  }

  .editor-slot {
    min-height: 0;
    overflow: hidden;
  }

  /* Narrow screens:the editor slides over the records as a right-hand drawer
     (positioned inside .body, so it never escapes to a viewport corner). */
  @media (max-width: 1100px) {
    .body.panel-open {
      grid-template-columns: 200px minmax(0, 1fr);
    }

    .editor-slot {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: min(520px, 100%);
      box-shadow: var(--shadow-lg);
      z-index: 5;
    }
  }

  .types {
    border-right: 1px solid var(--border);
    background: var(--surface-2);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow: auto;
  }

  .type-item {
    text-align: left;
    padding: 8px 12px;
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--text-2);
    font-size: 14px;
    cursor: pointer;
  }

  .type-item:hover {
    background: var(--surface-3);
  }

  .type-item.active {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
  }

  .records {
    padding: 24px 32px;
    overflow: auto;
    min-width: 0;
  }

  .records-header,
  table {
    max-width: 960px;
  }

  .records-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .records-header h2 {
    font-size: 18px;
    color: var(--text);
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 24px;
    max-width: 960px;
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius);
    color: var(--text-muted);
    font-size: 14px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th {
    text-align: left;
    padding: 8px;
    border-bottom: 1px solid var(--border);
    color: var(--text-muted);
    font-weight: 600;
  }

  td {
    padding: 8px;
    border-bottom: 1px solid var(--surface-3);
    color: var(--text);
  }

  tr.editing td {
    background: var(--accent-soft);
  }

  .row-actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }

  .hint {
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .error {
    margin-bottom: var(--space-3);
  }

  .records :global(.explain) {
    margin-bottom: var(--space-4);
  }
</style>
