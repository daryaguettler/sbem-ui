<script lang="ts">
  import {
    fetchComponentSchema,
    fetchComponentRecords,
    fetchComponentRecord,
    createComponentRecord,
    updateComponentRecord,
    type ComponentFieldDescriptor,
    type ComponentTypeSchema,
  } from '../../api/componentLibrary';
  // Self-import for recursive "create a related record inline" nesting
  // (e.g. Lighting's Schedule field opens a nested Year form). `svelte:self`
  // is deprecated in Svelte 5 in favor of this pattern.
  import SchemaForm from './SchemaForm.svelte';

  type Mode = 'create' | 'edit';

  let {
    componentType,
    mode,
    name = null,
    presetName = '',
    onSaved,
    onCancel,
  }: {
    componentType: string;
    mode: Mode;
    name?: string | null;
    presetName?: string;
    onSaved: (record: Record<string, unknown>) => void;
    onCancel: () => void;
  } = $props();

  let schema = $state<ComponentTypeSchema | null>(null);
  let values = $state<Record<string, unknown>>({});
  let relationOptions = $state<Record<string, string[]>>({});
  let loading = $state(true);
  let saving = $state(false);
  let error = $state<string | null>(null);

  // A field name currently showing a nested "create new related record" form,
  // e.g. clicking "+ New" next to Lighting's Schedule field opens a Year form.
  let creatingRelationFor = $state<string | null>(null);

  function defaultValueFor(field: ComponentFieldDescriptor): unknown {
    if (field.kind === 'boolean') return false;
    if (field.kind === 'enum') return field.options?.[0] ?? '';
    if (field.kind === 'number') return field.ge ?? 0;
    return '';
  }

  async function loadRelationOptions(field: ComponentFieldDescriptor) {
    if (field.kind !== 'relation' || !field.relationType) return;
    try {
      const records = await fetchComponentRecords(field.relationType);
      relationOptions = { ...relationOptions, [field.relationType]: records.map((r) => r.Name) };
    } catch {
      relationOptions = { ...relationOptions, [field.relationType]: [] };
    }
  }

  async function load() {
    loading = true;
    error = null;
    try {
      schema = await fetchComponentSchema(componentType);
      const initial: Record<string, unknown> =
        mode === 'edit' && name ? await fetchComponentRecord(componentType, name) : {};

      const nextValues: Record<string, unknown> = {};
      for (const field of schema.fields) {
        if (field.name in initial) {
          nextValues[field.name] = initial[field.name];
        } else if (field.name === 'Name') {
          nextValues.Name = presetName;
        } else if (field.required) {
          nextValues[field.name] = defaultValueFor(field);
        }
        await loadRelationOptions(field);
      }
      values = nextValues;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load form.';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    componentType;
    mode;
    name;
    load();
  });

  function updateValue(fieldName: string, value: unknown) {
    values = { ...values, [fieldName]: value };
  }

  function coerceForSubmit(): Record<string, unknown> {
    if (!schema) return values;
    const payload: Record<string, unknown> = {};
    for (const field of schema.fields) {
      const value = values[field.name];
      if (value === undefined || value === '') {
        if (field.required) payload[field.name] = value;
        continue;
      }
      payload[field.name] = field.kind === 'number' ? Number(value) : value;
    }
    return payload;
  }

  async function submit() {
    saving = true;
    error = null;
    try {
      const payload = coerceForSubmit();
      const record =
        mode === 'create'
          ? await createComponentRecord(componentType, payload)
          : await updateComponentRecord(componentType, name as string, payload);
      onSaved(record);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to save.';
    } finally {
      saving = false;
    }
  }

  function openCreateRelation(fieldName: string) {
    creatingRelationFor = fieldName;
  }

  function onRelationCreated(field: ComponentFieldDescriptor, record: Record<string, unknown>) {
    updateValue(field.name, record.Name);
    if (field.relationType) {
      relationOptions = {
        ...relationOptions,
        [field.relationType]: [...(relationOptions[field.relationType] ?? []), record.Name as string],
      };
    }
    creatingRelationFor = null;
  }
</script>

{#if loading}
  <p class="hint">Loading form...</p>
{:else if schema}
  <form class="schema-form" onsubmit={(event) => { event.preventDefault(); submit(); }}>
    {#each schema.fields as field (field.name)}
      <label class="field" class:wide={creatingRelationFor === field.name}>
        <span class="field-label">
          {field.title}{#if field.required}<span class="required">*</span>{/if}
        </span>

        {#if field.kind === 'relation'}
          <div class="relation-row">
            <select
              value={values[field.name] ?? ''}
              onchange={(event) => updateValue(field.name, (event.currentTarget as HTMLSelectElement).value)}
            >
              <option value="" disabled>Choose {field.relationType}...</option>
              {#each relationOptions[field.relationType ?? ''] ?? [] as optionName}
                <option value={optionName}>{optionName}</option>
              {/each}
            </select>
            <button type="button" class="secondary" onclick={() => openCreateRelation(field.name)}>
              + New {field.relationType}
            </button>
          </div>
          {#if creatingRelationFor === field.name && field.relationType}
            <div class="nested-form">
              <SchemaForm
                componentType={field.relationType}
                mode="create"
                onSaved={(record: Record<string, unknown>) => onRelationCreated(field, record)}
                onCancel={() => (creatingRelationFor = null)}
              />
            </div>
          {/if}
        {:else if field.kind === 'enum'}
          <select
            value={values[field.name] ?? ''}
            onchange={(event) => updateValue(field.name, (event.currentTarget as HTMLSelectElement).value)}
          >
            {#each field.options ?? [] as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
        {:else if field.kind === 'boolean'}
          <input
            type="checkbox"
            checked={Boolean(values[field.name])}
            onchange={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).checked)}
          />
        {:else if field.kind === 'number'}
          <input
            type="number"
            step="any"
            min={field.ge ?? field.gt}
            max={field.le ?? field.lt}
            value={values[field.name] ?? ''}
            oninput={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).value)}
          />
        {:else}
          <input
            type="text"
            disabled={field.name === 'Name' && mode === 'edit'}
            value={values[field.name] ?? ''}
            oninput={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).value)}
          />
        {/if}
      </label>
    {/each}

    {#if error}
      <p class="error">{error}</p>
    {/if}

    <div class="actions">
      <button type="button" class="secondary" onclick={onCancel}>Cancel</button>
      <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
    </div>
  </form>
{/if}

<style>
  /* Two columns where there's room -- these records have a lot of fields. A field
     whose nested "create related record" form is open takes the full width. */
  .schema-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    align-items: start;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 14px;
    color: #374151;
    min-width: 0;
  }

  .field.wide,
  .actions,
  .error {
    grid-column: 1 / -1;
  }

  .field-label {
    font-weight: 600;
  }

  .required {
    color: #dc2626;
    margin-left: 2px;
  }

  input[type='text'],
  input[type='number'],
  select {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 8px 12px;
    font: inherit;
    min-width: 0;
  }

  input[type='checkbox'] {
    width: 18px;
    height: 18px;
  }

  .relation-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .relation-row select {
    flex: 1;
  }

  .nested-form {
    margin-top: 8px;
    padding: 12px;
    border: 1px dashed #93c5fd;
    border-radius: 8px;
    background: #eff6ff;
  }

  .hint {
    font-size: 13px;
    color: #6b7280;
  }

  .error {
    margin: 0;
    font-size: 13px;
    color: #dc2626;
  }

  .actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 4px;
  }

  button {
    border: none;
    border-radius: 6px;
    background: #2563eb;
    color: #ffffff;
    padding: 8px 14px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
  }

  .secondary {
    background: #ffffff;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
