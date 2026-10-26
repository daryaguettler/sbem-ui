<script lang="ts">
  import { componentMapStore } from '../../stores/componentMapStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { componentTreeStore } from '../../stores/componentTreeStore';
  import SelectorCoverageGrid from './SelectorCoverageGrid.svelte';
  import SchemaForm from '../componentLibrary/SchemaForm.svelte';
  import HelpTip from '../HelpTip.svelte';
  import {
    buildComponentLevels,
    getSelectorAtPath,
    previewSelectorNames,
  } from '../../utils/componentMapTree';

  let { path }: { path: string } = $props();

  const componentLevels = buildComponentLevels();
  const level = $derived(componentLevels.find((entry) => entry.path === path));
  const componentType = $derived($componentTreeStore.nodesByPath[path]?.componentType ?? null);
  const selector = $derived(
    $componentMapStore.map ? getSelectorAtPath($componentMapStore.map, path) : null
  );
  const sourceFields = $derived(selector?.source_fields || []);
  const suffix = $derived(selector?.suffix || '');
  const preview = $derived(
    previewSelectorNames(
      sourceFields,
      $semanticFieldsStore.fields.map((field) => ({ name: field.name, options: field.options })),
      suffix || undefined
    )
  );

  // A library record being created/edited from the coverage grid. It replaces the
  // selector editor inside this side panel instead of floating over the page.
  let recordEdit = $state<{ name: string; exists: boolean } | null>(null);

  $effect(() => {
    path;
    recordEdit = null;
  });

  function toggleField(fieldName: string) {
    if (sourceFields.includes(fieldName)) {
      componentMapStore.unlinkField(path, fieldName);
      return;
    }
    componentMapStore.linkField(path, fieldName);
  }

  function updateSuffix(value: string) {
    componentMapStore.setSelector(path, sourceFields, value || undefined);
  }

  function removeMapping() {
    componentMapStore.removeSelector(path);
  }

  function collapseChildren() {
    if (sourceFields.length === 0) return;
    componentMapStore.collapseChildren(path);
  }
</script>

{#if level && recordEdit && componentType}
  <div class="editor">
    <div class="record-header">
      <button type="button" class="btn btn-ghost btn-sm" onclick={() => (recordEdit = null)}>← Back to selector</button>
      <h3>{recordEdit.exists ? 'Edit' : 'New'} {componentType}</h3>
      <p class="path">{recordEdit.name}</p>
    </div>
    {#key recordEdit.name}
      <SchemaForm
        {componentType}
        mode={recordEdit.exists ? 'edit' : 'create'}
        name={recordEdit.exists ? recordEdit.name : null}
        presetName={recordEdit.name}
        onSaved={() => (recordEdit = null)}
        onCancel={() => (recordEdit = null)}
      />
    {/key}
  </div>
{:else if level}
  <div class="editor">
    <div class="header">
      <div>
        <h3>{level.displayName}</h3>
        <p class="path">{path}</p>
      </div>
    </div>

    <p class="help">
      Which characteristics choose the record used here?
      <HelpTip
        text="Each combination of the ticked fields' options picks one library record, named by joining the option values with '_'. With nothing ticked, this component uses the nearest parent's selector, if any."
      />
    </p>

    <div class="field-list">
      {#each $semanticFieldsStore.fields as field}
        <label class="field-row">
          <input
            type="checkbox"
            checked={sourceFields.includes(field.name)}
            onchange={() => toggleField(field.name)}
          />
          <span>{field.name}</span>
          <span class="options">{field.options.join(', ') || 'no options'}</span>
        </label>
      {/each}
    </div>

    <label class="suffix-row">
      <span>
        Name suffix (optional)
        <HelpTip text="Appended to every generated record name, e.g. 'Res' turns 'SFH_Pre1975' into 'SFH_Pre1975_Res'. Use it to keep names unique." />
      </span>
      <input value={suffix} oninput={(event) => updateSuffix((event.currentTarget as HTMLInputElement).value)} />
    </label>

    {#if componentType && sourceFields.length > 0}
      <SelectorCoverageGrid
        {componentType}
        {sourceFields}
        {suffix}
        semanticFields={$semanticFieldsStore.fields.map((field) => ({ name: field.name, options: field.options }))}
        onOpenRecord={(name, exists) => (recordEdit = { name, exists })}
      />
    {:else}
      <div class="preview">
        <strong>{preview.count} generated names</strong>
        {#if preview.samples.length > 0}
          <ul>
            {#each preview.samples as name}
              <li>{name}</li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}

    <div class="actions">
      <button
        type="button"
        class="btn btn-secondary"
        onclick={collapseChildren}
        disabled={sourceFields.length === 0}
        title="Remove the selectors on everything below this component so they all inherit this one"
      >
        Collapse children
      </button>
      <button type="button" class="btn btn-danger" onclick={removeMapping} disabled={!selector}>
        Clear selector
      </button>
    </div>
  </div>
{:else}
  <p class="empty">Select a component to configure its selector.</p>
{/if}

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .record-header {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    padding-bottom: 10px;
    border-bottom: 1px dashed var(--border-strong);
  }

  .header h3,
  .record-header h3 {
    font-size: 16px;
    color: var(--text);
  }

  .path {
    font-size: 11px;
    color: var(--text-faint);
    font-family: var(--font-mono);
    overflow-wrap: anywhere;
  }

  .help,
  .empty {
    font-size: 13px;
    color: var(--text-muted);
  }

  .field-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 220px;
    overflow: auto;
  }

  .field-row {
    display: grid;
    grid-template-columns: auto 120px 1fr;
    gap: 8px;
    align-items: center;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 13px;
    color: var(--text);
  }

  .options {
    color: var(--text-muted);
    font-size: 12px;
  }

  .suffix-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
    color: var(--text-2);
  }

  .suffix-row input {
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    padding: 8px 10px;
    font: inherit;
  }

  .preview {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
    background: var(--surface-2);
    font-size: 13px;
    color: var(--text-2);
  }

  .preview ul {
    margin: 8px 0 0;
    padding-left: 18px;
  }

  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
</style>
