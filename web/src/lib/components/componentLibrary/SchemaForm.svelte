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
  import Icon from '../Icon.svelte';
  import { uValue } from '../../utils/optionValues';

  type Mode = 'create' | 'edit';
  /** One construction layer as the API carries it: outside layer first. */
  type Layer = { ConstructionMaterial: string; Thickness: number | string };

  let {
    componentType,
    mode,
    name = null,
    presetName = '',
    copyFrom = null,
    trail = [],
    onSaved,
    onCancel,
  }: {
    componentType: string;
    mode: Mode;
    name?: string | null;
    presetName?: string;
    /** Create mode: start from this existing record's values (the name stays presetName). */
    copyFrom?: string | null;
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
  /** Material conductivities, so a construction shows its U-value as layers change. */
  let conductivity = $state<Record<string, number>>({});
  /** Existing records of this type, offered as "Copy values from…" in create mode. */
  let sameTypeNames = $state<string[]>([]);
  let copySource = $state('');
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
    if (field.kind === 'layers') return [{ ConstructionMaterial: '', Thickness: 0.1 }];
    return '';
  }

  /** Record names for each related type, fetched once per type and in parallel
   * (a Year form has twelve Week fields). */
  async function loadRelationOptions(fields: ComponentFieldDescriptor[]) {
    const relationTypes = [
      ...new Set(fields.filter((f) => f.relationType).map((f) => f.relationType as string)),
    ];
    const entries = await Promise.all(
      relationTypes.map(async (relationType) => {
        try {
          const records = await fetchComponentRecords(relationType);
          if (relationType === 'ConstructionMaterial') {
            conductivity = Object.fromEntries(records.map((r) => [r.Name, Number(r.Conductivity)]));
          }
          return [relationType, records.map((r) => r.Name).sort((a, b) => a.localeCompare(b))] as const;
        } catch (err) {
          // an empty picker reads as broken; say why it is empty
          error = `Couldn't load the ${relationType} list: ${err instanceof Error ? err.message : 'request failed'}`;
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
      const source = mode === 'edit' ? name : copyFrom;
      const initial: Record<string, unknown> = source ? await fetchComponentRecord(componentType, source) : {};
      copySource = mode === 'create' && copyFrom ? copyFrom : '';

      const nextValues: Record<string, unknown> = {};
      for (const field of schema.fields) {
        if (field.name === 'Name' && mode === 'create') {
          nextValues.Name = presetName;
        } else if (field.name in initial) {
          nextValues[field.name] = initial[field.name];
        } else if (field.required) {
          nextValues[field.name] = defaultValueFor(field);
        }
      }
      await loadRelationOptions(schema.fields);
      if (mode === 'create') {
        sameTypeNames = (await fetchComponentRecords(componentType).catch(() => [])).map((r) => r.Name);
      }
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
    copyFrom;
    untrack(load);
  });

  function updateValue(fieldName: string, value: unknown) {
    values = { ...values, [fieldName]: value };
  }

  /** Fill every field but Name from an existing record of this type. */
  async function copyValuesFrom(source: string) {
    copySource = source;
    if (!schema || !source) return;
    try {
      const record = await fetchComponentRecord(componentType, source);
      const next = { ...values };
      for (const field of schema.fields) {
        if (field.name !== 'Name' && field.name in record) next[field.name] = record[field.name];
      }
      values = next;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to copy values.';
    }
  }

  const layersOf = (fieldName: string) => (values[fieldName] as Layer[] | undefined) ?? [];

  function setLayers(fieldName: string, layers: Layer[]) {
    updateValue(fieldName, layers);
  }

  function moveLayer(fieldName: string, index: number, delta: number) {
    const layers = [...layersOf(fieldName)];
    const target = index + delta;
    if (target < 0 || target >= layers.length) return;
    [layers[index], layers[target]] = [layers[target], layers[index]];
    setLayers(fieldName, layers);
  }

  const totalThickness = (fieldName: string) =>
    layersOf(fieldName).reduce((sum, layer) => sum + (Number(layer.Thickness) || 0), 0);

  function coerceForSubmit(): Record<string, unknown> {
    if (!schema) return values;
    const payload: Record<string, unknown> = {};
    for (const field of schema.fields) {
      const value = values[field.name];
      if (value === undefined || value === '') {
        if (field.required) payload[field.name] = value;
        continue;
      }
      if (field.kind === 'layers') {
        payload[field.name] = (value as Layer[]).map((layer) => ({
          ConstructionMaterial: layer.ConstructionMaterial,
          Thickness: Number(layer.Thickness),
        }));
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
    const layerFields = (schema?.fields ?? []).filter((field) => field.kind === 'layers');
    if (layerFields.some((field) => layersOf(field.name).length === 0 || layersOf(field.name).some((l) => !l.ConstructionMaterial))) {
      error = 'Add at least one layer and choose a material for every layer.';
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
        <button type="button" class="btn btn-ghost btn-sm" onclick={onCancel}><Icon name="arrow-left" size={14} />Back</button>
        <span class="trail">
          {#each trail as crumb}<span>{crumb}</span><span class="sep"><Icon name="chevron-right" size={12} /></span>{/each}
          <strong>New {componentType}</strong>
        </span>
      </nav>
    {/if}

    <form class="schema-form field-grid" onsubmit={(event) => { event.preventDefault(); submit(); }}>
      {#if mode === 'create' && sameTypeNames.length > 0}
        <div class="field copy-field">
          <span>Copy values from</span>
          <Select
            value={copySource}
            options={sameTypeNames.map((optionName) => ({ value: optionName, label: optionName }))}
            placeholder={`Start from an existing ${componentType}…`}
            onChange={copyValuesFrom}
          />
        </div>
      {/if}
      {#each schema.fields as field (field.name)}
        {#if field.kind === 'layers'}
          <fieldset class="field layers-field">
            <legend>
              {field.title} <span class="field-hint">outside <Icon name="arrow-right" size={12} /> inside</span>{#if field.required}<span class="required" aria-hidden="true">*</span>{/if}
            </legend>
            {#each layersOf(field.name) as layer, index}
              <div class="layer-row">
                <span class="layer-index" aria-hidden="true">{index + 1}</span>
                <span class="relation-pick">
                  <Select
                    value={layer.ConstructionMaterial}
                    options={(relationOptions[field.relationType ?? ''] ?? []).map((optionName) => ({ value: optionName, label: optionName }))}
                    placeholder="Choose material…"
                    ariaLabel={`Layer ${index + 1} material`}
                    onChange={(value) =>
                      setLayers(field.name, layersOf(field.name).map((l, i) => (i === index ? { ...l, ConstructionMaterial: value } : l)))}
                  />
                </span>
                <input
                  class="thickness"
                  type="number"
                  step="any"
                  min="0"
                  max="2"
                  aria-label={`Layer ${index + 1} thickness (m)`}
                  value={layer.Thickness}
                  oninput={(event) =>
                    setLayers(field.name, layersOf(field.name).map((l, i) =>
                      i === index ? { ...l, Thickness: (event.currentTarget as HTMLInputElement).value } : l))}
                />
                <span class="unit">m</span>
                <button type="button" class="btn btn-ghost btn-sm" title="Move outwards" aria-label={`Move layer ${index + 1} outwards`} disabled={index === 0} onclick={() => moveLayer(field.name, index, -1)}><Icon name="arrow-up" size={14} /></button>
                <button type="button" class="btn btn-ghost btn-sm" title="Move inwards" aria-label={`Move layer ${index + 1} inwards`} disabled={index === layersOf(field.name).length - 1} onclick={() => moveLayer(field.name, index, 1)}><Icon name="arrow-down" size={14} /></button>
                <button type="button" class="btn btn-ghost btn-sm" title="Remove layer" aria-label={`Remove layer ${index + 1}`} onclick={() => setLayers(field.name, layersOf(field.name).filter((_, i) => i !== index))}><Icon name="x" size={14} /></button>
              </div>
            {/each}
            <div class="layer-foot">
              <button type="button" class="btn btn-secondary btn-sm" onclick={() => setLayers(field.name, [...layersOf(field.name), { ConstructionMaterial: '', Thickness: 0.1 }])}>
                + Add layer
              </button>
              <span class="field-hint">
                Total {totalThickness(field.name).toFixed(3)} m{#if uValue(layersOf(field.name), conductivity) !== null}{' · '}<strong
                    >U {uValue(layersOf(field.name), conductivity)?.toFixed(2)} W/m²K</strong
                  >{/if}
              </span>
            </div>
          </fieldset>
        {:else if field.kind === 'boolean'}
          <div class="field">
            <label class="check">
              <input
                type="checkbox"
                checked={Boolean(values[field.name])}
                onchange={(event) => updateValue(field.name, (event.currentTarget as HTMLInputElement).checked)}
              />
              {field.title}{#if field.required}<span class="required" aria-hidden="true">*</span>{/if}
            </label>
          </div>
        {:else}
        <div class="field">
          <label for={fieldId(field.name)}>
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
              <button type="button" class="btn btn-secondary" onclick={() => openCreateRelation(field.name)}>
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
        {/if}
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
    gap: var(--space-2);
    margin-bottom: var(--space-4);
    padding-bottom: var(--space-3);
    border-bottom: 1px dashed var(--border-strong);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .trail {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1);
    min-width: 0;
  }

  .trail strong {
    color: var(--text);
    font-weight: 600;
  }

  .sep {
    display: inline-flex;
    color: var(--text-faint);
  }

  /* Two columns where the panel is wide enough, one otherwise. */
  .schema-form {
    --field-min: 200px;
  }

  .schema-form > * {
    min-width: 0;
  }

  .actions,
  .error,
  .copy-field,
  .layers-field {
    grid-column: 1 / -1;
  }

  .layers-field {
    min-width: 0;
    border: none;
  }

  .layers-field legend {
    margin-bottom: var(--space-1);
  }

  .layer-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .layer-index {
    width: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: 300;
    text-align: right;
  }

  input.thickness {
    width: 90px;
    flex: none;
  }

  .unit {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: 300;
  }

  .layer-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .field label,
  .field legend {
    overflow-wrap: anywhere;
  }

  .check {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--control-h);
  }

  .required {
    color: var(--err-text);
    margin-left: 2px;
  }

  .relation-row {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  .relation-pick {
    flex: 1;
    min-width: 0;
  }

  /* Pinned to the bottom of the scrolling side panel so Save is always reachable. */
  .actions {
    position: sticky;
    bottom: 0;
    justify-content: flex-end;
    margin: var(--space-1) calc(-1 * var(--panel-pad, 0px)) 0;
    padding: var(--space-3) var(--panel-pad, 0px);
    background: var(--surface);
    border-top: 1px solid var(--border);
  }
</style>
