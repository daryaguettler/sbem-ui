<script lang="ts">
  import SchemaForm from '../components/componentLibrary/SchemaForm.svelte';
  import {
    fetchComponentTypes,
    fetchComponentRecords,
    deleteComponentRecord,
    type ComponentRecord,
  } from '../api/componentLibrary';

  let types = $state<string[]>([]);
  let selectedType = $state<string | null>(null);
  let records = $state<ComponentRecord[]>([]);
  let loadingTypes = $state(true);
  let loadingRecords = $state(false);
  let error = $state<string | null>(null);

  type PanelState = { mode: 'closed' } | { mode: 'create' } | { mode: 'edit'; name: string };
  let panel = $state<PanelState>({ mode: 'closed' });
  let dialog = $state<HTMLDialogElement | null>(null);

  // The <dialog> is only rendered while the panel is open, so this fires on mount.
  // showModal() gives us Escape-to-close and a focus trap for free.
  $effect(() => {
    if (dialog && !dialog.open) dialog.showModal();
  });

  function onDialogClick(event: MouseEvent) {
    // A click that lands on the dialog element itself is a click on the backdrop.
    if (event.target === dialog) closePanel();
  }

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
    <h1>Component Library</h1>
    <p class="subtitle">
      Author the real engineering-parameter records (LPD, infiltration rates, DHW efficiency, ...) that
      the Component Map's selectors reference. Build these first -- the component map is generated from
      them, not the other way around.
    </p>
  </header>

  <div class="body">
    <aside class="types">
      {#if loadingTypes}
        <p class="hint">Loading types...</p>
      {:else}
        {#each types as type}
          <button type="button" class="type-item" class:active={type === selectedType} onclick={() => selectType(type)}>
            {type}
          </button>
        {/each}
      {/if}
    </aside>

    <section class="records">
      {#if selectedType}
        <div class="records-header">
          <h3>{selectedType}</h3>
          <button type="button" onclick={openCreate}>+ New {selectedType}</button>
        </div>

        {#if error}
          <p class="error">{error}</p>
        {/if}

        {#if loadingRecords}
          <p class="hint">Loading records...</p>
        {:else if records.length === 0}
          <p class="hint">No {selectedType} records yet.</p>
        {:else}
          <table>
            <thead>
              <tr><th>Name</th><th></th></tr>
            </thead>
            <tbody>
              {#each records as record}
                <tr>
                  <td>{record.Name}</td>
                  <td class="row-actions">
                    <button type="button" class="secondary" onclick={() => openEdit(record.Name)}>Edit</button>
                    <button type="button" class="danger" onclick={() => removeRecord(record.Name)}>Delete</button>
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
  </div>
</div>

{#if panel.mode !== 'closed' && selectedType}
  <dialog class="editor" bind:this={dialog} onclose={closePanel} onclick={onDialogClick}>
    <div class="editor-body">
      <header class="editor-header">
        <h2>{panel.mode === 'create' ? `New ${selectedType}` : `Edit ${panel.mode === 'edit' ? panel.name : ''}`}</h2>
        <button type="button" class="close" onclick={closePanel} aria-label="Close">&times;</button>
      </header>
      <SchemaForm
        componentType={selectedType}
        mode={panel.mode === 'create' ? 'create' : 'edit'}
        name={panel.mode === 'edit' ? panel.name : null}
        onSaved={onSaved}
        onCancel={closePanel}
      />
    </div>
  </dialog>
{/if}

<style>
  .workflow {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .workflow-header {
    padding: 24px 32px;
    border-bottom: 1px solid #e5e7eb;
  }

  .workflow-header h1 {
    margin: 0 0 4px;
    font-size: 24px;
    color: #111827;
  }

  .subtitle {
    margin: 0;
    font-size: 14px;
    color: #6b7280;
    max-width: 720px;
    line-height: 1.5;
  }

  .body {
    flex: 1;
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr);
    min-height: 0;
    overflow: hidden;
  }

  .types {
    border-right: 1px solid #e5e7eb;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    overflow: auto;
  }

  .type-item {
    text-align: left;
    padding: 10px 12px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #374151;
    font-size: 14px;
    cursor: pointer;
  }

  .type-item:hover {
    background: #f3f4f6;
  }

  .type-item.active {
    background: #eff6ff;
    color: #2563eb;
    font-weight: 600;
  }

  .records {
    padding: 24px 32px;
    overflow: auto;
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

  .records-header h3 {
    margin: 0;
    font-size: 18px;
    color: #111827;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th {
    text-align: left;
    padding: 8px;
    border-bottom: 1px solid #e5e7eb;
    color: #6b7280;
    font-weight: 600;
  }

  td {
    padding: 8px;
    border-bottom: 1px solid #f3f4f6;
    color: #111827;
  }

  .row-actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }

  /* The create/edit form is a centered dialog rather than a narrow right-hand rail:
     component records have a lot of fields, and relation fields open a nested form
     inside this one, which needs the width. */
  .editor {
    width: min(680px, calc(100vw - 48px));
    max-height: min(85vh, 900px);
    padding: 0;
    border: none;
    border-radius: 12px;
    box-shadow: 0 20px 45px rgba(17, 24, 39, 0.25);
    overflow: auto;
  }

  .editor::backdrop {
    background: rgba(17, 24, 39, 0.45);
  }

  .editor-body {
    padding: 24px;
  }

  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 20px;
  }

  .editor-header h2 {
    margin: 0;
    font-size: 18px;
    color: #111827;
  }

  .close {
    background: transparent;
    color: #6b7280;
    font-size: 22px;
    line-height: 1;
    padding: 2px 8px;
  }

  .close:hover {
    color: #111827;
  }

  .hint {
    font-size: 14px;
    color: #6b7280;
  }

  .error {
    font-size: 13px;
    color: #dc2626;
  }

  button {
    border: none;
    border-radius: 6px;
    background: #2563eb;
    color: #ffffff;
    padding: 8px 12px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
  }

  .secondary {
    background: #ffffff;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .danger {
    background: #ffffff;
    color: #dc2626;
    border: 1px solid #fecaca;
  }
</style>
