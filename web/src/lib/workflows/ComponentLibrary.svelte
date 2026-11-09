<script lang="ts">
  import SchemaForm from '../components/componentLibrary/SchemaForm.svelte';
  import ScheduleVariability from '../components/componentLibrary/ScheduleVariability.svelte';
  import ScheduleEditor from '../components/componentLibrary/ScheduleEditor.svelte';
  import SidePanel from '../components/SidePanel.svelte';
  import ComponentPriorEditor from '../components/priors/ComponentPriorEditor.svelte';
  import { keyField } from '../utils/componentPriors';
  import Icon from '../components/Icon.svelte';
  import {
    fetchComponentTypes,
    fetchComponentRecords,
    deleteComponentRecord,
    checkComponentExistence,
    type ComponentRecord,
  } from '../api/componentLibrary';
  import { componentMapStore } from '../stores/componentMapStore';
  import { componentTreeStore } from '../stores/componentTreeStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { dirtyKinds } from '../stores/projectArtifacts';
  import { partRulesStore } from '../stores/partRulesStore';
  import { GENERATED_PREFIX, optionsInUse } from '../utils/partRules';
  import { buildSelectorCombinations, collectSelectors } from '../utils/componentMapTree';
  import Explain from '../components/Explain.svelte';
  import { HELP } from '../help';
  const help = HELP.componentLibrary;

  const HIDDEN_TYPES = ['Day', 'Week'];
  const typeLabel = (type: string) => (type === 'Year' ? 'Schedule' : type);
  let types = $state<string[]>([]);
  let selectedType = $state<string | null>(null);
  let records = $state<ComponentRecord[]>([]);
  let loadingTypes = $state(true);
  let loadingRecords = $state(false);
  let error = $state<string | null>(null);
  /** Records by type, the records the model needs, or the per-building schedule noise on top of them. */
  let view = $state<'records' | 'needed' | 'variability'>('records');

  type PanelState =
    | { mode: 'closed' }
    | { mode: 'create'; presetName?: string; copyFrom?: string }
    | { mode: 'edit'; name: string };
  let panel = $state<PanelState>({ mode: 'closed' });

  /** Every record name the characteristics and model parts require, by library type. */
  type Needed = { type: string; records: Array<{ name: string; exists: boolean }> };
  let needed = $state<Needed[]>([]);
  let loadingNeeded = $state(false);
  /** Records part rules build on every save; hidden unless asked for, and not for editing. */
  let showGenerated = $state(false);
  const rules = $derived($partRulesStore.rules);
  const generatedCount = $derived(records.filter((r) => r.Name.startsWith(GENERATED_PREFIX)).length);
  const shownRecords = $derived(showGenerated ? records : records.filter((r) => !r.Name.startsWith(GENERATED_PREFIX)));

  async function loadTypes() {
    loadingTypes = true;
    try {
      const { types: fetched } = await fetchComponentTypes();
      // a schedule's Days and Weeks are edited inside its Year (ScheduleEditor)
      types = fetched.filter((type) => !HIDDEN_TYPES.includes(type));
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

  function openDuplicate(name: string) {
    panel = { mode: 'create', copyFrom: name };
  }

  function closePanel() {
    panel = { mode: 'closed' };
  }

  function onSaved() {
    panel = { mode: 'closed' };
    loadRecords();
    if (view === 'needed') loadNeeded();
  }

  /** Open a needed record: edit it if it exists, otherwise create it with its name filled in. */
  function openNeeded(type: string, name: string, exists: boolean) {
    if (selectedType !== type) {
      selectedType = type;
      loadRecords();
    }
    panel = exists ? { mode: 'edit', name } : { mode: 'create', presetName: name };
  }

  async function loadNeeded() {
    const map = $componentMapStore.map;
    if (!map && !rules) {
      needed = [];
      return;
    }
    loadingNeeded = true;
    error = null;
    try {
      const fields = $semanticFieldsStore.fields.map((field) => ({ name: field.name, options: field.options }));
      const namesByType = new Map<string, Set<string>>();
      // with part rules, the options they use; otherwise every name the map's selectors build
      for (const [path, options] of Object.entries(rules ? optionsInUse(rules, Object.fromEntries(fields.map((field) => [field.name, field.options]))) : {})) {
        const type = $componentTreeStore.nodesByPath[path]?.componentType;
        if (!type) continue;
        namesByType.set(type, new Set([...(namesByType.get(type) ?? []), ...options]));
      }
      for (const selector of rules || !map ? [] : collectSelectors(map)) {
        const type = $componentTreeStore.nodesByPath[selector.path]?.componentType;
        if (!type) continue;
        const names = namesByType.get(type) ?? new Set<string>();
        for (const combination of buildSelectorCombinations(selector.source_fields, fields, selector.suffix)) {
          names.add(combination.name);
        }
        namesByType.set(type, names);
      }
      needed = await Promise.all(
        [...namesByType].map(async ([type, names]) => {
          const existence = await checkComponentExistence(type, [...names]);
          return { type, records: [...names].sort().map((name) => ({ name, exists: Boolean(existence[name]) })) };
        })
      );
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to check the library.';
    } finally {
      loadingNeeded = false;
    }
  }

  function showNeeded() {
    view = 'needed';
    panel = { mode: 'closed' };
    loadNeeded();
  }

  const missingCount = $derived(needed.reduce((sum, group) => sum + group.records.filter((r) => !r.exists).length, 0));

  async function removeRecord(name: string) {
    if (!selectedType) return;
    if (!confirm(`Delete ${typeLabel(selectedType)} record "${name}"? This cannot be undone.`)) return;
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
    <div class="tabs" role="tablist">
      <button type="button" role="tab" aria-selected={view === 'records'} class:active={view === 'records'} onclick={() => { view = 'records'; panel = { mode: 'closed' }; }}>
        Records
      </button>
      <button type="button" role="tab" aria-selected={view === 'needed'} class:active={view === 'needed'} onclick={showNeeded}>
        {rules ? 'Options in use' : 'Needed by the model'}
      </button>
      <button type="button" role="tab" aria-selected={view === 'variability'} class:active={view === 'variability'} onclick={() => (view = 'variability')}>
        Schedule variability <span class="tag tag-warn">in progress</span>
      </button>
    </div>
  </header>

  {#snippet editor()}
    {#if panel.mode !== 'closed' && selectedType}
      <div class="editor-slot">
        <SidePanel
          title={panel.mode === 'create' ? `New ${typeLabel(selectedType)}` : `Edit ${panel.mode === 'edit' ? panel.name : ''}`}
          subtitle={typeLabel(selectedType)}
          onClose={closePanel}
        >
          {#key `${selectedType}:${panel.mode}:${panel.mode === 'edit' ? panel.name : (panel.presetName ?? '') + (panel.copyFrom ?? '')}`}
            {@const Form = selectedType === 'Year' ? ScheduleEditor : SchemaForm}
            <Form
              componentType={selectedType}
              mode={panel.mode === 'create' ? 'create' : 'edit'}
              name={panel.mode === 'edit' ? panel.name : null}
              presetName={panel.mode === 'create' ? (panel.presetName ?? '') : ''}
              copyFrom={panel.mode === 'create' ? (panel.copyFrom ?? null) : null}
              onSaved={onSaved}
              onCancel={closePanel}
            />
            <!-- uncertainty is for the components parts pick (walls, lighting, ...), which all have a key number -->
            {#if panel.mode === 'edit' && keyField(selectedType)}
              <section class="uncertainty">
                <h3>Uncertainty</h3>
                <ComponentPriorEditor type={selectedType} name={panel.name} standalone />
              </section>
            {/if}
          {/key}
        </SidePanel>
      </div>
    {/if}
  {/snippet}

  {#if view === 'variability'}
    <div class="variability-view">
      <!-- shortcut: Save and Preview need globi's schedule variability (feature/add-variability-to-component-libs); drop this note after the merge -->
      <p class="callout callout-warn">
        In progress: this is still being connected to GloBI. You can explore the settings, but <strong>Save</strong> and the
        <strong>Preview</strong> will show an error until then, and batch runs don't apply it yet.
      </p>
      <ScheduleVariability />
    </div>
  {:else if view === 'needed'}
    <div class="body needed-body" class:panel-open={panel.mode !== 'closed'}>
      <section class="records">
        <div class="records-header">
          <h2>{rules ? 'Options your part rules use' : 'Needed by the model'} <Explain text={help.needed} tip /></h2>
          <button type="button" class="btn btn-secondary" onclick={loadNeeded} disabled={loadingNeeded}>Refresh</button>
        </div>
        <Explain text={help.needed} />
        {#if $dirtyKinds.length > 0}
          <p class="hint">Building Characteristics has unsaved changes; this list uses what is on screen there.</p>
        {/if}
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        {#if loadingNeeded}
          <p class="hint">Checking the library…</p>
        {:else if needed.length === 0}
          <p class="empty empty-box">Nothing is chosen yet. On Component Map, choose an option for each part.</p>
        {:else}
          <p class="summary-line">
            {#if missingCount === 0}
              <span class="status-ok"><Icon name="check" size={14} />Every record the model needs exists.</span>
            {:else}
              <span class="status-warn"><Icon name="alert" size={14} />{missingCount} record{missingCount === 1 ? '' : 's'} still missing.</span>
            {/if}
            {rules
              ? `Edit an option here to change every building that uses it. Records named ${GENERATED_PREFIX}… are rebuilt from your part rules on every save.`
              : 'Records these point to (assemblies, constructions, schedules) are picked inside each form; create them there with + New or under their own type.'}
          </p>
          {#each needed as group (group.type)}
            <h3 class="group-title">{typeLabel(group.type)} <span class="hint">{group.records.filter((r) => r.exists).length} of {group.records.length} exist</span></h3>
            <table class="data-table">
              <tbody>
                {#each group.records as record (record.name)}
                  <tr>
                    <td><code>{record.name}</code></td>
                    <td>
                      {#if record.exists}
                        <span class="status-ok"><Icon name="check" size={14} />Exists</span>
                      {:else}
                        <span class="status-err"><Icon name="x" size={14} />Missing</span>
                      {/if}
                    </td>
                    <td>
                      <div class="actions row-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick={() => openNeeded(group.type, record.name, record.exists)}>
                          {#if record.exists}Edit{:else}<Icon name="plus" size={14} />Create{/if}
                        </button>
                      </div>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/each}
        {/if}
      </section>
      {@render editor()}
    </div>
  {:else}
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
            {typeLabel(type)}
          </button>
        {/each}
      {/if}
    </nav>

    <section class="records">
      {#if selectedType}
        <div class="records-header">
          <h2>{typeLabel(selectedType)} <Explain text={help.records} tip /></h2>
          <button type="button" class="btn" onclick={openCreate}><Icon name="plus" size={14} />Add {typeLabel(selectedType)}</button>
        </div>
        <Explain text={help.records} />
        {#if generatedCount > 0}
          <label class="hint generated-toggle">
            <input type="checkbox" bind:checked={showGenerated} />
            Show the {generatedCount} record{generatedCount === 1 ? '' : 's'} built from part rules ({GENERATED_PREFIX}…); they are rebuilt on every save
          </label>
        {/if}

        {#if error}
          <p class="error" role="alert">{error}</p>
        {/if}

        {#if loadingRecords}
          <p class="hint">Loading records…</p>
        {:else if shownRecords.length === 0}
          <div class="empty empty-box empty-state">
            <p>No {typeLabel(selectedType)} records yet.</p>
            <button type="button" class="btn btn-secondary" onclick={openCreate}><Icon name="plus" size={14} />Add the first one</button>
          </div>
        {:else}
          <table class="data-table">
            <thead>
              <tr><th>Name</th><th><span class="visually-hidden">Actions</span></th></tr>
            </thead>
            <tbody>
              {#each shownRecords as record}
                <tr class:editing={panel.mode === 'edit' && panel.name === record.Name}>
                  <td>{record.Name}</td>
                  <td>
                    <div class="actions row-actions">
                      <button type="button" class="btn btn-secondary btn-sm" onclick={() => openEdit(record.Name)}>Edit</button>
                      <button type="button" class="btn btn-secondary btn-sm" onclick={() => openDuplicate(record.Name)}>Duplicate</button>
                      <button type="button" class="btn btn-danger btn-sm" onclick={() => removeRecord(record.Name)}>Delete</button>
                    </div>
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

    {@render editor()}
  </div>
  {/if}
</div>

<style>
  /* Tab underlines sit on the header's own bottom rule. */
  .tabs {
    margin: var(--space-3) 0 calc(-1 * var(--space-5));
    border-bottom: none;
  }

  .body.needed-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .body.needed-body.panel-open {
    grid-template-columns: minmax(0, 1fr) minmax(400px, 560px);
  }

  .summary-line {
    margin-bottom: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .group-title {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: var(--space-4) 0 var(--space-2);
    font-size: var(--text-md);
    font-weight: 600;
  }

  .variability-view {
    flex: 1;
    overflow: auto;
    padding: var(--space-6) var(--space-8);
  }

  .body {
    position: relative;
    flex: 1;
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    min-height: 0;
    overflow: hidden;
  }

  /* The editor docks as a third column; records stay visible beside it. */
  .uncertainty { margin-top: var(--space-5); padding-top: var(--space-4); border-top: 1px solid var(--border); }
  .uncertainty h3 { margin: 0 0 var(--space-2); font-size: var(--text-md); }
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
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    overflow: auto;
  }

  .type-item {
    text-align: left;
    padding: var(--space-2) var(--space-3);
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-md);
    cursor: pointer;
  }

  .type-item:hover {
    background: var(--surface-3);
    color: var(--text);
  }

  .type-item.active {
    background: var(--surface-3);
    color: var(--text);
    font-weight: 600;
  }

  .records {
    padding: var(--space-6) var(--space-8);
    overflow: auto;
    min-width: 0;
  }

  .records-header,
  .data-table,
  .empty-box {
    max-width: 960px;
  }

  .records-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    margin-bottom: var(--space-4);
  }

  .records-header h2 {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text);
  }

  .generated-toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-3);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }

  tr.editing td {
    background: var(--accent-soft);
  }

  .row-actions {
    justify-content: flex-end;
  }

  .error {
    margin-bottom: var(--space-3);
  }

  .records :global(.explain) {
    margin-bottom: var(--space-4);
  }
</style>
