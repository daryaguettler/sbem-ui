<script lang="ts">
  import { componentMapStore } from '../../stores/componentMapStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { componentTreeStore } from '../../stores/componentTreeStore';
  import SelectorCoverageGrid from './SelectorCoverageGrid.svelte';
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

{#if level}
  <div class="editor">
    <div class="header">
      <div>
        <h3>{level.displayName}</h3>
        <p class="path">{path}</p>
      </div>
    </div>

    <p class="help">Choose semantic fields that determine which component record is selected for this path.</p>

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
      Suffix
      <input value={suffix} oninput={(event) => updateSuffix((event.currentTarget as HTMLInputElement).value)} />
    </label>

    {#if componentType && sourceFields.length > 0}
      <SelectorCoverageGrid
        {componentType}
        {sourceFields}
        {suffix}
        semanticFields={$semanticFieldsStore.fields.map((field) => ({ name: field.name, options: field.options }))}
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
      <button type="button" class="secondary" onclick={collapseChildren} disabled={sourceFields.length === 0}>
        Collapse children
      </button>
      <button type="button" class="danger" onclick={removeMapping} disabled={!selector}>
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

  .header h3 {
    margin: 0;
    font-size: 16px;
    color: #111827;
  }

  .path {
    margin: 4px 0 0;
    font-size: 11px;
    color: #9ca3af;
    font-family: monospace;
  }

  .help,
  .empty {
    margin: 0;
    font-size: 13px;
    color: #6b7280;
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
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    font-size: 13px;
    color: #111827;
  }

  .options {
    color: #6b7280;
    font-size: 12px;
  }

  .suffix-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
    color: #374151;
  }

  .suffix-row input {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 8px 10px;
    font: inherit;
  }

  .preview {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px;
    background: #f9fafb;
    font-size: 13px;
    color: #374151;
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

  button {
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    padding: 8px 12px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
  }

  .secondary {
    background: #ffffff;
    color: #2563eb;
    border: 1px solid #2563eb;
  }

  .danger {
    background: #dc2626;
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
