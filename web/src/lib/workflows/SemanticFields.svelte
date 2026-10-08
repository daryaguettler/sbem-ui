<script lang="ts">
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import { gisDataset } from '../stores/projectStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import type {
    SemanticField,
    SemanticFieldTemplateSummary,
    SemanticFieldsPreview,
    ValidationResult,
  } from '../types/semanticFields';
  import { formatSavedAt, saveArtifact } from '../api/artifacts';
  import { loadSavedArtifact, markSaved, savedAt } from '../stores/projectArtifacts';
  import { downloadFromResponse, downloadText } from '../utils/download';
  import {
    createEmptyField,
    ensureTransformationRule,
    initCategoricalGroups,
    initNumericRanges,
    parseOptionsText,
  } from '../utils/semanticFieldRules';

  let templates: SemanticFieldTemplateSummary[] = [];
  let loading = true;
  let error: string | null = null;
  let validation: ValidationResult | null = null;
  let preview: SemanticFieldsPreview | null = null;
  let previewLoading = false;
  let previewTimer: ReturnType<typeof setTimeout> | null = null;
  let optionsText = '';
  let saving = false;

  onMount(async () => {
    await loadTemplates();
  });

  $: selectedField =
    $semanticFieldsStore.fields.find((field) => field.id === $semanticFieldsStore.selectedFieldId) ||
    null;

  $: if ($semanticFieldsStore.editorMode === 'edit' && selectedField) {
    schedulePreview();
  }

  async function loadTemplates() {
    loading = true;
    error = null;
    try {
      const response = await fetch('/api/semantic-fields/templates');
      const data = await response.json();
      templates = data.templates || [];
    } catch (e) {
      error = 'Failed to load templates.';
    } finally {
      loading = false;
    }
  }

  async function loadTemplate(filename: string) {
    try {
      const response = await fetch(`/api/semantic-fields/templates/${filename}`);
      const templateData = await response.json();
      semanticFieldsStore.loadFromTemplate(templateData);
      const firstField = $semanticFieldsStore.fields[0];
      if (firstField) {
        semanticFieldsStore.setSelectedField(firstField.id);
        optionsText = firstField.options.join(', ');
      }
      schedulePreview();
    } catch (e) {
      error = 'Failed to load template.';
    }
  }

  function startFromScratch() {
    semanticFieldsStore.startFromScratch();
    const field = createEmptyField();
    semanticFieldsStore.addField(field);
    semanticFieldsStore.setSelectedField(field.id);
    optionsText = '';
  }

  function selectField(field: SemanticField) {
    semanticFieldsStore.setSelectedField(field.id);
    optionsText = field.options.join(', ');
  }

  function updateSelectedField(updates: Partial<SemanticField>) {
    if (!selectedField) return;

    let nextField: SemanticField = { ...selectedField, ...updates };
    if ('options' in updates || 'dataType' in updates || 'type' in updates) {
      nextField = ensureTransformationRule(nextField, $semanticFieldsStore.gisColumns);
    }

    semanticFieldsStore.updateField(selectedField.id, nextField);
  }

  function updateOptionsFromText(value: string) {
    optionsText = value;
    const options = parseOptionsText(value);
    let nextField = ensureTransformationRule(
      {
        ...selectedField!,
        options,
      },
      $semanticFieldsStore.gisColumns
    );

    if (nextField.transformationRule?.type === 'numeric_range') {
      nextField = {
        ...nextField,
        transformationRule: {
          ...nextField.transformationRule,
          numericRanges: initNumericRanges(options),
        },
      };
    }

    semanticFieldsStore.updateField(selectedField!.id, nextField);
    schedulePreview();
  }

  function updateSourceColumn(sourceColumn: string) {
    if (!selectedField) return;

    let nextField = ensureTransformationRule(
      {
        ...selectedField,
        transformationRule: {
          ...(selectedField.transformationRule || {
            id: crypto.randomUUID(),
            type: selectedField.dataType === 'numeric' ? 'numeric_range' : 'categorical_mapping',
            sourceColumn,
            targetField: selectedField.name,
          }),
          sourceColumn,
          targetField: selectedField.name,
        },
      },
      $semanticFieldsStore.gisColumns
    );

    if (nextField.transformationRule?.type === 'categorical_mapping') {
      nextField = {
        ...nextField,
        transformationRule: {
          ...nextField.transformationRule,
          categoricalGroups: initCategoricalGroups(
            sourceColumn,
            nextField.options,
            $semanticFieldsStore.gisColumns
          ),
        },
      };
    }

    semanticFieldsStore.updateField(selectedField.id, nextField);
    schedulePreview();
  }

  function updateNumericRange(index: number, key: 'min' | 'max' | 'label', value: string) {
    if (!selectedField?.transformationRule?.numericRanges) return;

    const ranges = selectedField.transformationRule.numericRanges.map((range, rangeIndex) =>
      rangeIndex === index
        ? {
            ...range,
            [key]: key === 'label' ? value : Number(value),
          }
        : range
    );

    updateSelectedField({
      transformationRule: {
        ...selectedField.transformationRule,
        numericRanges: ranges,
      },
    });
    schedulePreview();
  }

  function updateCategoricalGroup(index: number, groupLabel: string) {
    if (!selectedField?.transformationRule?.categoricalGroups) return;

    const groups = selectedField.transformationRule.categoricalGroups.map((group, groupIndex) =>
      groupIndex === index ? { ...group, groupLabel } : group
    );

    updateSelectedField({
      transformationRule: {
        ...selectedField.transformationRule,
        categoricalGroups: groups,
      },
    });
    schedulePreview();
  }

  function addField() {
    const field = createEmptyField();
    semanticFieldsStore.addField(field);
    semanticFieldsStore.setSelectedField(field.id);
    optionsText = '';
  }

  function schedulePreview() {
    if (!$gisDataset?.validated || $semanticFieldsStore.fields.length === 0) {
      preview = null;
      return;
    }

    if (previewTimer) {
      clearTimeout(previewTimer);
    }

    previewTimer = setTimeout(refreshPreview, 300);
  }

  async function refreshPreview() {
    previewLoading = true;
    try {
      const response = await fetch('/api/semantic-fields/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Preview failed.');
      }
      preview = data;
      validation = data.validation || null;
    } catch (e) {
      preview = null;
    } finally {
      previewLoading = false;
    }
  }

  async function validateFields() {
    const response = await fetch('/api/semantic-fields/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
    });
    validation = await response.json();
  }

  async function saveToProject() {
    saving = true;
    error = null;
    try {
      const file = await saveArtifact(
        'semantic-fields',
        semanticFieldsStore.buildApiPayload($semanticFieldsStore)
      );
      markSaved('semantic-fields', file.modifiedAt);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to save to the project.';
    } finally {
      saving = false;
    }
  }

  /** Discard unsaved edits and read the project's saved semantic-fields.yaml back in. */
  async function loadFromProject() {
    error = null;
    try {
      if (!(await loadSavedArtifact('semantic-fields'))) {
        error = 'No semantic fields have been saved in this project yet.';
        return;
      }
      const firstField = $semanticFieldsStore.fields[0];
      if (firstField) {
        semanticFieldsStore.setSelectedField(firstField.id);
        optionsText = firstField.options.join(', ');
      }
      schedulePreview();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load the saved fields.';
    }
  }

  async function exportFields() {
    const response = await fetch('/api/semantic-fields/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
    });
    const yaml = await response.text();
    downloadText(yaml, 'semantic-fields.yml', 'application/x-yaml');
  }

  async function exportEnrichedGis() {
    try {
      const response = await fetch('/api/gis/export-enriched', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Export failed.');
      }
      await downloadFromResponse(response, 'buildings-with-semantic-fields.geojson');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Export failed.';
    }
  }

  let savedGis: string | null = null;

  /** Write the GIS with semantic fields applied into the project (gis/buildings.geojson). */
  async function saveEnrichedGis() {
    try {
      const response = await fetch('/api/gis/export-enriched?save=true', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Save failed.');
      savedGis = data.path;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Save failed.';
    }
  }

  $: selectedPreview = preview?.field_previews.find(
    (entry) => entry.field_name === selectedField?.name
  );
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Semantic Fields</h1>
    <p class="subtitle">Define transformation rules and preview deterministic semantic fields on your GIS data</p>
  </div>

  <div class="workflow-content">
    {#if !$gisDataset?.validated}
      <WorkflowGuide
        title="Load GIS data first"
        message="Semantic field rules are applied to the cleaned GIS dataset from the previous workflow."
        actionLabel="Go to GIS Cleaning"
        actionWorkflow="gis-cleaning"
      />
    {/if}

    {#if $semanticFieldsStore.editorMode === 'browse'}
      <div class="panel">
        <h2>Choose a starting point</h2>
        {#if loading}
          <p>Loading templates...</p>
        {:else}
          <div class="templates-grid">
            {#each templates as template}
              <button type="button" class="template-card" onclick={() => loadTemplate(template.filename)}>
                <h3>{template.name}</h3>
                <p>{template.description || 'Template'}</p>
              </button>
            {/each}
            {#if $savedAt['semantic-fields']}
              <button type="button" class="template-card saved" onclick={loadFromProject}>
                <h3>Saved in this project</h3>
                <p>{formatSavedAt($savedAt['semantic-fields'])} to semantic-fields.yaml.</p>
              </button>
            {/if}
            <button type="button" class="template-card scratch" onclick={startFromScratch}>
              <h3>Start from Scratch</h3>
              <p>Create fields and define numeric or categorical mapping rules.</p>
            </button>
          </div>
        {/if}
      </div>
    {:else}
      <div class="panel config-panel">
        <div class="field-grid">
          <label>
            Config name
            <input
              value={$semanticFieldsStore.configName}
              oninput={(event) =>
                semanticFieldsStore.setConfigMeta({
                  configName: (event.currentTarget as HTMLInputElement).value,
                })}
            />
          </label>
          <label>
            Building ID column
            <input value={$semanticFieldsStore.buildingIdCol} readonly />
          </label>
          <label>
            Number of floors column
            <input value={$semanticFieldsStore.numFloorsCol} readonly />
          </label>
        </div>
      </div>

      <div class="editor-layout">
        <aside class="field-list">
          <div class="list-header">
            <h2>Fields</h2>
            <button type="button" class="small" onclick={addField}>Add</button>
          </div>
          {#if $semanticFieldsStore.fields.length === 0}
            <p class="empty">Add a field to begin.</p>
          {:else}
            {#each $semanticFieldsStore.fields as field}
              <button
                type="button"
                class="field-item"
                class:active={field.id === $semanticFieldsStore.selectedFieldId}
                onclick={() => selectField(field)}
              >
                <strong>{field.name || 'Untitled field'}</strong>
                <span class="badge {field.type}">{field.type}</span>
              </button>
            {/each}
          {/if}
        </aside>

        <section class="rule-editor">
          {#if selectedField}
            <h2>Edit field</h2>
            <div class="field-grid">
              <label>
                Name
                <input
                  value={selectedField.name}
                  oninput={(event) =>
                    updateSelectedField({ name: (event.currentTarget as HTMLInputElement).value })}
                />
              </label>
              <label>
                Type
                <select
                  value={selectedField.type}
                  onchange={(event) => {
                    const type = (event.currentTarget as HTMLSelectElement).value as SemanticField['type'];
                    updateSelectedField({
                      type,
                      requiresPrior: type === 'stochastic',
                      transformationRule: type === 'stochastic' ? undefined : selectedField.transformationRule,
                    });
                  }}
                >
                  <option value="deterministic">Deterministic</option>
                  <option value="stochastic">Stochastic</option>
                </select>
              </label>
              <label>
                Options (comma-separated)
                <input
                  value={optionsText}
                  oninput={(event) => updateOptionsFromText((event.currentTarget as HTMLInputElement).value)}
                />
              </label>
            </div>

            {#if selectedField.type === 'deterministic'}
              <div class="field-grid">
                <label>
                  GIS source column
                  <select
                    value={selectedField.transformationRule?.sourceColumn || ''}
                    onchange={(event) =>
                      updateSourceColumn((event.currentTarget as HTMLSelectElement).value)}
                  >
                    <option value="">Select column</option>
                    {#each $semanticFieldsStore.gisColumns as column}
                      <option value={column.name}>{column.name}</option>
                    {/each}
                  </select>
                </label>
                <label>
                  Rule type
                  <select
                    value={selectedField.transformationRule?.type || 'categorical_mapping'}
                    onchange={(event) => {
                      const type = (event.currentTarget as HTMLSelectElement).value as 'numeric_range' | 'categorical_mapping';
                      updateSelectedField({
                        dataType: type === 'numeric_range' ? 'numeric' : 'categorical',
                        transformationRule: {
                          ...(selectedField.transformationRule || {
                            id: crypto.randomUUID(),
                            sourceColumn: '',
                            targetField: selectedField.name,
                          }),
                          type,
                          numericRanges:
                            type === 'numeric_range'
                              ? initNumericRanges(selectedField.options)
                              : undefined,
                          categoricalGroups:
                            type === 'categorical_mapping' && selectedField.transformationRule?.sourceColumn
                              ? initCategoricalGroups(
                                  selectedField.transformationRule.sourceColumn,
                                  selectedField.options,
                                  $semanticFieldsStore.gisColumns
                                )
                              : undefined,
                        },
                      });
                    }}
                  >
                    <option value="numeric_range">Numeric ranges</option>
                    <option value="categorical_mapping">Categorical mapping</option>
                  </select>
                </label>
              </div>

              {#if selectedField.transformationRule?.type === 'numeric_range'}
                <h3>Numeric range rules</h3>
                <p class="help">Define how source values map onto semantic options. Example: YEARBLT &lt; 1975 → pre_1975.</p>
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Option</th>
                        <th>Min</th>
                        <th>Max</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each selectedField.transformationRule.numericRanges || [] as range, index}
                        <tr>
                          <td>
                            <input
                              value={range.label}
                              oninput={(event) =>
                                updateNumericRange(index, 'label', (event.currentTarget as HTMLInputElement).value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              value={range.min}
                              oninput={(event) =>
                                updateNumericRange(index, 'min', (event.currentTarget as HTMLInputElement).value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              value={range.max}
                              oninput={(event) =>
                                updateNumericRange(index, 'max', (event.currentTarget as HTMLInputElement).value)}
                            />
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}

              {#if selectedField.transformationRule?.type === 'categorical_mapping'}
                <h3>Categorical mapping rules</h3>
                <p class="help">Map each source value to one of the semantic field options.</p>
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Source value</th>
                        <th>Semantic option</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each selectedField.transformationRule.categoricalGroups || [] as group, index}
                        <tr>
                          <td>{group.sourceValues.join(', ')}</td>
                          <td>
                            <select
                              value={group.groupLabel}
                              onchange={(event) =>
                                updateCategoricalGroup(index, (event.currentTarget as HTMLSelectElement).value)}
                            >
                              {#each selectedField.options as option}
                                <option value={option}>{option}</option>
                              {/each}
                            </select>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            {:else}
              <p class="help">Stochastic fields are sampled later using prior trees. No GIS transformation rule is needed.</p>
            {/if}

            <button type="button" class="danger" onclick={() => semanticFieldsStore.removeField(selectedField.id)}>
              Remove field
            </button>
          {:else}
            <p class="empty">Select or add a field to edit its rules.</p>
          {/if}
        </section>

        <aside class="preview-panel">
          <h2>Preview</h2>
          {#if previewLoading}
            <p>Updating preview...</p>
          {:else if selectedPreview}
            <div class="stats">
              <span>{selectedPreview.stats.coverage_percent}% mapped</span>
              <span>{selectedPreview.stats.unmapped_count} unmapped rows</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{selectedPreview.source_column}</th>
                    <th>{selectedPreview.field_name}</th>
                  </tr>
                </thead>
                <tbody>
                  {#each selectedPreview.samples as sample}
                    <tr>
                      <td>{sample.source_value ?? ''}</td>
                      <td>{sample.semantic_value ?? '—'}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="empty">Preview appears once rules are configured.</p>
          {/if}
        </aside>
      </div>

      <div class="actions">
        <button
          type="button"
          onclick={saveToProject}
          disabled={saving || $semanticFieldsStore.fields.length === 0}
        >
          {saving ? 'Saving...' : 'Save to project'}
        </button>
        {#if $savedAt['semantic-fields']}
          <button type="button" class="secondary" onclick={loadFromProject}>Revert to saved</button>
        {/if}
        <button type="button" onclick={validateFields}>Validate rules</button>
        <button type="button" onclick={exportFields} disabled={$semanticFieldsStore.fields.length === 0}>
          Export YAML
        </button>
        <button
          type="button"
          class="secondary"
          onclick={exportEnrichedGis}
          disabled={!validation?.valid || $semanticFieldsStore.fields.length === 0}
        >
          Apply and download GIS
        </button>
        <button
          type="button"
          class="secondary"
          onclick={saveEnrichedGis}
          disabled={!validation?.valid || $semanticFieldsStore.fields.length === 0}
        >
          Apply and save GIS
        </button>
      </div>

      <p class="saved-status">
        {formatSavedAt($savedAt['semantic-fields'])}{#if savedGis} · GIS saved to {savedGis}{/if}
      </p>

      {#if validation}
        <div class="panel" class:invalid={!validation.valid}>
          {#if validation.valid}
            <p>Rules are valid and ready to export.</p>
          {:else}
            <ul>
              {#each validation.errors as issue}
                <li>{issue}</li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
    {/if}

    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>
</section>

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
  }

  .subtitle,
  .help,
  .empty {
    margin: 0;
    color: #6b7280;
    font-size: 14px;
  }

  .help {
    margin-bottom: 12px;
  }

  .workflow-content {
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .panel,
  .field-list,
  .rule-editor,
  .preview-panel {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 20px;
    background: #ffffff;
  }

  .config-panel {
    padding-bottom: 12px;
  }

  .editor-layout {
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr) 280px;
    gap: 16px;
    min-height: 420px;
  }

  .list-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .list-header h2,
  .rule-editor h2,
  .preview-panel h2 {
    margin: 0;
    font-size: 18px;
  }

  .field-item {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    color: #111827;
    font-weight: 400;
    cursor: pointer;
    text-align: left;
  }

  .field-item.active {
    border-color: #2563eb;
    background: #eff6ff;
  }

  .templates-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  .template-card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px;
    background: #ffffff;
    color: #111827;
    font-weight: 400;
    text-align: left;
    cursor: pointer;
  }

  .template-card h3 {
    margin: 0 0 8px;
    font-size: 16px;
    color: #111827;
  }

  .template-card p {
    margin: 0;
    color: #6b7280;
    font-size: 13px;
  }

  .template-card.scratch {
    border-style: dashed;
    background: #f9fafb;
  }

  .field-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
  }

  input,
  select {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 8px 10px;
    font: inherit;
  }

  button {
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    padding: 10px 16px;
    cursor: pointer;
    font-weight: 600;
  }

  .small {
    padding: 6px 10px;
    font-size: 12px;
  }

  .secondary {
    background: #ffffff;
    color: #2563eb;
    border: 1px solid #2563eb;
  }

  .danger {
    background: #dc2626;
    margin-top: 12px;
  }

  .badge {
    font-size: 10px;
    text-transform: uppercase;
    padding: 4px 8px;
    border-radius: 999px;
    font-weight: 700;
  }

  .badge.deterministic {
    background: #dbeafe;
    color: #1e40af;
  }

  .badge.stochastic {
    background: #fce7f3;
    color: #9d174d;
  }

  .table-wrap {
    overflow: auto;
    margin-bottom: 16px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th,
  td {
    border-bottom: 1px solid #e5e7eb;
    padding: 10px;
    text-align: left;
  }

  .stats {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    font-size: 13px;
    color: #374151;
  }

  .actions {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }

  .saved-status {
    margin: -12px 0 0;
    font-size: 13px;
    color: #6b7280;
  }

  .template-card.saved {
    border-color: #bfdbfe;
    background: #eff6ff;
  }

  .invalid {
    border-color: #fecaca;
    background: #fef2f2;
    color: #b91c1c;
  }

  .error {
    color: #dc2626;
  }

  @media (max-width: 1100px) {
    .editor-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
