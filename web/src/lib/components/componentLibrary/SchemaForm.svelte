<script lang="ts">
  import { untrack } from 'svelte';
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
  import Select from '../Select.svelte';

  type Mode = 'create' | 'edit';

  let {
    componentType,
    mode,
    name = null,
    presetName = '',
    trail = [],
    onSaved,
    onCancel,
  }: {
    componentType: string;
    mode: Mode;
    name?: string | null;
    presetName?: string;
    /** Parent forms when this one was opened from a "+ New" relation button, outermost first. */
    trail?: string[];
    onSaved: (record: Record<string, unknown>) => void;
    onCancel: () => void;
  } = $props();

  const uid = $props.id();
  const fieldId = (fieldName: string) => `${uid}-${fieldName}`;

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

  /** Record names for each related type, fetched once per type and in parallel
   * (a Year form has twelve Week fields). */
  async function loadRelationOptions(fields: ComponentFieldDescriptor[]) {
    const relationTypes = [
      ...new Set(fields.filter((f) => f.kind === 'relation' && f.relationType).map((f) => f.relationType as string)),
    ];
    const entries = await Promise.all(
      relationTypes.map(async (relationType) => {
        try {
          const records = await fetchComponentRecords(relationType);
          return [relationType, records.map((r) => r.Name)] as const;
        } catch {
          return [relationType, [] as string[]] as const;
        }
      })
    );
    relationOptions = { ...relationOptions, ...Object.fromEntries(entries) };
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
      }
      await loadRelationOptions(schema.fields);
      values = nextValues;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load form.';
    } finally {
      loading = false;
    }
  }

  // Reload when the record changes; load() reads/writes local state, so keep it untracked.
  $effect(() => {
    componentType;
    mode;
    name;
    untrack(load);
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
    // The dropdowns aren't native selects, so the browser no longer enforces `required`.
    const missing = (schema?.fields ?? []).filter(
      (field) => field.kind === 'relation' && field.required && !values[field.name]
    );
    if (missing.length > 0) {
      error = `Choose ${missing.map((field) => field.title).join(', ')} first.`;
      return;
    }
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
  <p class="hint">Loading form…</p>
{:else if schema}
  <!-- While a related record is being created, this form stays mounted (so its values
       survive) but hidden, and the nested form takes its place: one form on screen at
       a time, with a breadcrumb back up the stack. -->
  <div class="form-frame" hidden={creatingRelationFor !== null}>
    {#if trail.length > 0}
      <nav class="crumbs" aria-label="Nested record">
        <button type="button" class="btn btn-ghost btn-sm back" onclick={onCancel}>← Back</button>
        <span class="trail">
          {#each trail as crumb}<span>{crumb}</span><span class="sep">›</span>{/each}
          <strong>New {componentType}</strong>
        </span>
      </nav>
    {/if}

    <form class="schema-form" onsubmit={(event) => { event.preventDefault(); submit(); }}>
      {#each schema.fields as field (field.name)}
        <div class="field" class:checkbox-field={field.kind === 'boolean'}>
          <label class="field-label" for={fieldId(field.name)}>
            {field.title}{#if field.required}<span class="required" aria-hidden="true">*</span>{/if}
          </label>

          {#if field.kind === 'relation'}
            <div class="relation-row">
              <span class="relation-pick">
                <Select
                  id={fieldId(field.name)}
                  value={String(values[field.name] ?? '')}
                  options={(relationOptions[field.relationType ?? ''] ?? []).map((optionName) => ({
                    value: optionName,
                    label: optionName,
                  }))}
                  placeholder={`Choose ${field.relationType}…`}
                  onChange={(value) => updateValue(field.name, value)}
                />
              </span>
              <button type="button" class="btn btn-secondary btn-sm" onclick={() => openCreateRelation(field.name)}>
                + New
              </button>
            </div>
          {:else if field.kind === 'enum'}
            <Select
              id={fieldId(field.name)}
              value={String(values[field.name] ?? '')}
              options={(field.options ?? []).map((option) => ({ value: option, label: option }))}
              onChange={(value) => updateValue(field.name, value)}
            />
          {:else if field.kind === 'boolean'}
            <input
              id={fieldId(field.name)}
              type="checkbox"
              checked={Boolean(values[field.name])}
              onchange={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).checked)}
            />
          {:else if field.kind === 'number'}
            <input
              id={fieldId(field.name)}
              type="number"
              step="any"
              min={field.ge ?? field.gt}
              max={field.le ?? field.lt}
              value={values[field.name] ?? ''}
              oninput={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).value)}
            />
          {:else}
            <input
              id={fieldId(field.name)}
              type="text"
              disabled={field.name === 'Name' && mode === 'edit'}
              value={values[field.name] ?? ''}
              oninput={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).value)}
            />
          {/if}
        </div>
      {/each}

      {#if error}
        <p class="error" role="alert">{error}</p>
      {/if}

      <div class="actions">
        <button type="button" class="btn btn-secondary" onclick={onCancel}>Cancel</button>
        <button type="submit" class="btn" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
      </div>
    </form>
  </div>

  {#if creatingRelationFor}
    {@const field = schema.fields.find((f) => f.name === creatingRelationFor)}
    {#if field?.relationType}
      <SchemaForm
        componentType={field.relationType}
        mode="create"
        trail={[...trail, mode === 'edit' && name ? name : `New ${componentType}`]}
        onSaved={(record: Record<string, unknown>) => onRelationCreated(field, record)}
        onCancel={() => (creatingRelationFor = null)}
      />
    {/if}
  {/if}
{/if}

<style>
  .form-frame[hidden] {
    display: none;
  }

  .crumbs {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px dashed var(--border-strong);
    font-size: 12px;
    color: var(--text-muted);
  }

  .trail {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    min-width: 0;
  }

  .trail strong {
    color: var(--text);
  }

  .sep {
    color: var(--text-faint);
  }

  /* Two columns where the panel is wide enough, one otherwise. */
  .schema-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 16px;
    align-items: start;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 14px;
    color: var(--text-2);
    min-width: 0;
  }

  .checkbox-field {
    flex-direction: row-reverse;
    justify-content: flex-end;
    align-items: center;
    align-self: end;
    min-height: 38px;
  }

  .actions,
  .error {
    grid-column: 1 / -1;
  }

  .field-label {
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .required {
    color: var(--err-text);
    margin-left: 2px;
  }

  input[type='text'],
  input[type='number'] {
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    padding: 8px 10px;
    font: inherit;
    min-width: 0;
    width: 100%;
  }

  input:disabled {
    background: var(--surface-3);
    color: var(--text-muted);
  }

  input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--accent);
  }

  .relation-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .relation-pick {
    flex: 1;
  }

  .hint {
    font-size: 13px;
    color: var(--text-muted);
  }

  .error {
    font-size: 13px;
    color: var(--err-text);
  }

  /* Pinned to the bottom of the scrolling side panel so Save is always reachable. */
  .actions {
    position: sticky;
    bottom: 0;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin: 4px calc(-1 * var(--panel-pad, 0px)) 0;
    padding: 12px var(--panel-pad, 0px);
    background: var(--surface);
    border-top: 1px solid var(--border);
  }
</style>
