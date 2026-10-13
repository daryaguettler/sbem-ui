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
    syncNumericRanges,
  } from '../utils/semanticFieldRules';
  import HelpTip from '../components/HelpTip.svelte';
  import SemanticFieldAssist from '../components/SemanticFieldAssist.svelte';

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
    const previousRanges = selectedField!.transformationRule?.numericRanges;
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
          numericRanges: syncNumericRanges(previousRanges, options),
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

  function changeType(type: SemanticField['type']) {
    if (!selectedField) return;
    const rule = selectedField.transformationRule;
    const hasRule = Boolean(rule?.sourceColumn || rule?.numericRanges?.some((r) => r.min || r.max));
    if (
      type === 'stochastic' &&
      hasRule &&
      !confirm(`Switching "${selectedField.name || 'this field'}" to sampled removes its GIS rule. Continue?`)
    ) {
      return false;
    }
    updateSelectedField({
      type,
      requiresPrior: type === 'stochastic',
      transformationRule: type === 'stochastic' ? undefined : selectedField.transformationRule,
    });
    return true;
  }

  function removeSelectedField() {
    if (!selectedField) return;
    if (!confirm(`Remove the field "${selectedField.name || 'Untitled field'}"?`)) return;
    semanticFieldsStore.removeField(selectedField.id);
  }

  /** Take a reviewed AI draft into the editor; Validate/Save stay the user's call. */
  function applyDraft(draft: SemanticField) {
    if (!selectedField) return;
    semanticFieldsStore.updateField(selectedField.id, { ...draft, id: selectedField.id });
    optionsText = draft.options.join(', ');
    validation = null;
    schedulePreview();
  }

  function changeTemplate() {
    semanticFieldsStore.update((state) => ({ ...state, editorMode: 'browse' }));
  }

  /** Templates and saved files replace the current fields, so ask first when there are edits. */
  function confirmReplace(): boolean {
    return (
      $semanticFieldsStore.fields.length === 0 ||
      confirm('This replaces the fields you are editing. Unsaved changes will be lost. Continue?')
    );
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
    <p class="subtitle">Turn raw GIS columns into the building categories the model uses (e.g. age band, typology).</p>
  </div>

  <div class="workflow-content">
    {#if !$gisDataset?.validated}
      <WorkflowGuide
        title="Validate GIS data first"
        message="Rules are applied to your cleaned GIS data, so the preview needs it."
        actionLabel="Go to GIS Cleaning"
        actionWorkflow="gis-cleaning"
      />
    {/if}

    {#if $semanticFieldsStore.editorMode === 'browse'}
      <div class="panel">
        <div class="browse-header">
          <h2>Choose a starting point</h2>
          {#if $semanticFieldsStore.fields.length > 0}
            <button type="button" class="secondary" onclick={() => semanticFieldsStore.update((state) => ({ ...state, editorMode: 'edit' }))}>
              ← Back to editing
            </button>
          {/if}
        </div>
        {#if loading}
          <p>Loading templates...</p>
        {:else}
          <div class="templates-grid">
            {#each templates as template}
              <button type="button" class="template-card" onclick={() => confirmReplace() && loadTemplate(template.filename)}>
                <h3>{template.name}</h3>
                {#if template.description}<p>{template.description}</p>{/if}
              </button>
            {/each}
            {#if $savedAt['semantic-fields']}
              <button type="button" class="template-card saved" onclick={() => confirmReplace() && loadFromProject()}>
                <h3>Saved in this project</h3>
                <p>{formatSavedAt($savedAt['semantic-fields'])} to semantic-fields.yaml.</p>
              </button>
            {/if}
            <button type="button" class="template-card scratch" onclick={() => confirmReplace() && startFromScratch()}>
              <h3>Start from scratch</h3>
              <p>An empty list; add fields one by one.</p>
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
            Building ID column <span class="from-gis">(set in GIS Cleaning)</span>
            <input value={$semanticFieldsStore.buildingIdCol} readonly />
          </label>
          <label>
            Number of floors column <span class="from-gis">(set in GIS Cleaning)</span>
            <input value={$semanticFieldsStore.numFloorsCol} readonly />
          </label>
          <div class="config-actions">
            <button type="button" class="secondary" onclick={changeTemplate}>Change template</button>
          </div>
        </div>
      </div>

      <div class="editor-layout">
        <aside class="field-list">
          <div class="list-header">
            <h2>Fields</h2>
            <button type="button" class="small" onclick={addField}>+ Add field</button>
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
                <span class="badge {field.type}">{field.type === 'stochastic' ? 'sampled' : 'from GIS'}</span>
              </button>
            {/each}
          {/if}
        </aside>

        <section class="rule-editor">
          {#if selectedField}
            <h2>Edit field</h2>
            {#key selectedField.id}
              <SemanticFieldAssist
                field={selectedField}
                apiFields={semanticFieldsStore.buildApiPayload($semanticFieldsStore).fields}
                onApply={applyDraft}
              />
            {/key}
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
                <span>
                  Source
                  <HelpTip
                    text="From GIS: computed for every building by a rule on one of your columns (e.g. age band from year built). Sampled: your data doesn't record it (e.g. heating system), so it's drawn from probabilities you set in Prior Trees."
                  />
                </span>
                <select
                  value={selectedField.type}
                  onchange={(event) => {
                    const select = event.currentTarget as HTMLSelectElement;
                    const type = select.value as SemanticField['type'];
                    if (changeType(type) === false) select.value = selectedField.type;
                  }}
                >
                  <option value="deterministic">From GIS data (rule)</option>
                  <option value="stochastic">Sampled (set in Prior Trees)</option>
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
                  GIS column
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
                <h3>Ranges</h3>
                <p class="help">Each option covers a range of the column's values, e.g. 0–1974 → pre_1975.</p>
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
                <h3>Value mapping</h3>
                <p class="help">Pick which option each value in the column becomes.</p>
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Value in GIS</th>
                        <th>Becomes</th>
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
              <p class="help">Sampled fields don't need a GIS rule. Set their probabilities in Prior Trees.</p>
            {/if}

            <button type="button" class="danger" onclick={removeSelectedField}>
              Remove field
            </button>
          {:else}
            <p class="empty">Select or add a field to edit its rules.</p>
          {/if}
        </section>

        <aside class="preview-panel">
          <h2>Preview</h2>
          {#if previewLoading}
            <p>Updating preview…</p>
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
          {:else if !$gisDataset?.validated}
            <p class="empty">Validate your GIS data in step 1 to see a preview.</p>
          {:else if selectedField?.type === 'stochastic'}
            <p class="empty">Sampled fields have no GIS preview.</p>
          {:else if !selectedField?.transformationRule?.sourceColumn}
            <p class="empty">Pick a GIS column to see how buildings are classified.</p>
          {:else}
            <p class="empty">No preview yet. Check the rule for errors with Validate.</p>
          {/if}
        </aside>
      </div>

      <div class="actions">
        <div class="action-group">
          <button
            type="button"
            onclick={saveToProject}
            disabled={saving || $semanticFieldsStore.fields.length === 0}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          {#if $savedAt['semantic-fields']}
            <button type="button" class="secondary" onclick={() => confirmReplace() && loadFromProject()}>Revert</button>
          {/if}
          <button type="button" class="secondary" onclick={validateFields}>Validate</button>
        </div>
        <div class="action-group export-group" role="group" aria-label="Export">
          <span class="group-label">Export</span>
          <button
            type="button"
            class="secondary"
            onclick={exportFields}
            disabled={$semanticFieldsStore.fields.length === 0}
          >
            YAML
          </button>
          <button
            type="button"
            class="secondary"
            onclick={exportEnrichedGis}
            disabled={!validation?.valid || $semanticFieldsStore.fields.length === 0}
            title={validation?.valid ? 'Download your GIS data with these fields added as columns' : 'Validate the rules first'}
          >
            GIS with fields
          </button>
          <button
            type="button"
            class="secondary"
            onclick={saveEnrichedGis}
            disabled={!validation?.valid || $semanticFieldsStore.fields.length === 0}
            title={validation?.valid ? 'Save your GIS data with these fields added into the project (gis/buildings.geojson)' : 'Validate the rules first'}
          >
            Save GIS to project
          </button>
        </div>
      </div>

      <p class="saved-status">
        {formatSavedAt($savedAt['semantic-fields'])}{#if savedGis} · GIS saved to {savedGis}{/if}
      </p>

      {#if validation}
        <div class="panel" class:invalid={!validation.valid}>
          {#if validation.valid}
            <p><span aria-hidden="true">✓</span> Rules are valid.</p>
          {:else}
            <p class="problems"><span aria-hidden="true">✕</span> {validation.errors.length} problem{validation.errors.length === 1 ? '' : 's'} to fix:</p>
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
    border-bottom: 1px solid var(--border);
  }

  .workflow-header h1 {
    margin: 0 0 4px;
    font-size: 24px;
  }

  .subtitle,
  .help,
  .empty {
    margin: 0;
    color: var(--text-muted);
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
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    background: var(--surface);
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
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    font-weight: 400;
    cursor: pointer;
    text-align: left;
  }

  .field-item.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .templates-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  .template-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    background: var(--surface);
    color: var(--text);
    font-weight: 400;
    text-align: left;
    cursor: pointer;
  }

  .template-card h3 {
    margin: 0 0 8px;
    font-size: 16px;
    color: var(--text);
  }

  .template-card p {
    margin: 0;
    color: var(--text-muted);
    font-size: 13px;
  }

  .template-card.scratch {
    border-style: dashed;
    background: var(--surface-2);
  }

  .field-grid {
    align-items: end;
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
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    padding: 8px 10px;
    font: inherit;
  }

  button {
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: var(--on-accent);
    padding: 10px 16px;
    cursor: pointer;
    font-weight: 600;
  }

  .small {
    padding: 6px 10px;
    font-size: 12px;
  }

  .secondary {
    background: var(--surface);
    color: var(--accent);
    border: 1px solid var(--accent);
  }

  .danger {
    background: var(--danger);
    margin-top: 12px;
  }

  .badge {
    flex: none;
    white-space: nowrap;
    font-size: 10px;
    text-transform: uppercase;
    padding: 4px 8px;
    border-radius: 999px;
    font-weight: 700;
  }

  .badge.deterministic {
    background: var(--accent-soft);
    color: var(--accent-hover);
  }

  .badge.stochastic {
    background: color-mix(in srgb, var(--series-5) 18%, var(--surface));
    color: var(--text);
  }

  .table-wrap {
    overflow: auto;
    margin-bottom: 16px;
  }

  /* Inputs inside rule tables shrink to their cell instead of forcing a scrollbar. */
  td input,
  td select {
    width: 100%;
    min-width: 0;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th,
  td {
    border-bottom: 1px solid var(--border);
    padding: 10px;
    text-align: left;
  }

  .stats {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--text-2);
  }

  .actions {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .action-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .group-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .problems {
    font-weight: 600;
    margin-bottom: 6px;
  }

  .from-gis {
    font-weight: 400;
    color: var(--text-faint);
    font-size: 12px;
  }

  .config-actions {
    display: flex;
    align-items: flex-end;
    justify-content: flex-end;
  }

  .browse-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
  }

  .browse-header h2 {
    margin: 0;
  }

  .saved-status {
    margin: -12px 0 0;
    font-size: 13px;
    color: var(--text-muted);
  }

  .template-card.saved {
    border-color: var(--accent-border);
    background: var(--accent-soft);
  }

  .invalid {
    border-color: var(--err-border);
    background: var(--err-bg);
    color: var(--err-text);
  }

  .error {
    color: var(--err-text);
  }

  @media (max-width: 1100px) {
    .editor-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
