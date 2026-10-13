<script lang="ts">
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import { gisDataset } from '../stores/projectStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import type { GlobiColumnRole, GisColumnMappings } from '../types/gis';
  import type { GISColumn } from '../types/semanticFields';
  import { downloadFromResponse } from '../utils/download';

  let selectedFile: File | null = null;
  let uploading = false;
  let cleaning = false;
  let error: string | null = null;
  let columns: GISColumn[] = [];
  let roles: GlobiColumnRole[] = [];
  let validationIssues: string[] = [];
  let columnMappings: GisColumnMappings = {};
  let validateColumns = new Set<string>();
  let dropIncompleteRows = false;
  let incompleteRowCount = 0;
  let droppedRowCount = 0;
  let outputColumns: string[] = [];
  let sourceFormat: string | null = null;

  onMount(async () => {
    await refreshColumns();
  });

  function defaultValidateColumns(mappings: GisColumnMappings, roleList: GlobiColumnRole[]): Set<string> {
    const selected = new Set<string>();
    for (const role of roleList) {
      const source = mappings[role.key];
      if (source && (role.required || role.recommended)) {
        selected.add(source);
      }
    }
    return selected;
  }

  function applyDatasetPayload(data: {
    columns?: GISColumn[];
    columnMappings?: GisColumnMappings;
    validatedColumns?: string[];
    filename?: string;
    rowCount?: number;
    validated?: boolean;
    columnCount?: number;
    droppedRowCount?: number;
    outputColumns?: string[];
    sourceFormat?: string | null;
  }) {
    columns = data.columns || [];
    if (data.columnMappings) {
      columnMappings = { ...data.columnMappings };
    }
    if (data.validatedColumns?.length) {
      validateColumns = new Set(data.validatedColumns);
    } else if (roles.length > 0) {
      validateColumns = defaultValidateColumns(columnMappings, roles);
    }

    if (data.filename !== undefined) {
      gisDataset.set({
        filename: data.filename,
        rowCount: data.rowCount || 0,
        validated: Boolean(data.validated),
        columnCount: data.columnCount ?? columns.length,
      });
    }

    droppedRowCount = data.droppedRowCount ?? droppedRowCount;
    outputColumns = data.outputColumns || outputColumns;
    sourceFormat = data.sourceFormat ?? sourceFormat;

    semanticFieldsStore.setGISColumns(columns);
  }

  async function refreshColumns() {
    try {
      const response = await fetch('/api/gis/columns');
      const data = await response.json();
      roles = (data.roles || []).map(normalizeRole);
      applyDatasetPayload({
        columns: data.columns || [],
        columnMappings: data.columnMappings || data.dataset?.columnMappings,
        validatedColumns: data.dataset?.validatedColumns,
        filename: data.dataset?.filename,
        rowCount: data.dataset?.rowCount,
        validated: data.dataset?.validated,
        columnCount: data.dataset?.columns?.length,
        droppedRowCount: data.dataset?.droppedRowCount,
        outputColumns: data.dataset?.outputColumns,
        sourceFormat: data.dataset?.sourceFormat,
      });
    } catch (e) {
      error = 'Failed to load GIS session.';
    }
  }

  function normalizeRole(role: Record<string, unknown>): GlobiColumnRole {
    return {
      key: String(role.key),
      label: String(role.label),
      yamlKey: role.yaml_key ? String(role.yaml_key) : null,
      required: Boolean(role.required),
      recommended: Boolean(role.recommended),
      requiredGroup: role.required_group ? String(role.required_group) : undefined,
      description: role.description ? String(role.description) : undefined,
    };
  }

  async function loadRoles() {
    const response = await fetch('/api/gis/column-roles');
    const data = await response.json();
    roles = (data.roles || []).map(normalizeRole);
  }

  async function uploadFile() {
    if (!selectedFile) {
      error = 'Choose a CSV or GeoJSON file first.';
      return;
    }

    uploading = true;
    error = null;
    validationIssues = [];

    try {
      if (roles.length === 0) {
        await loadRoles();
      }

      const formData = new FormData();
      formData.append('file', selectedFile);
      const response = await fetch('/api/gis/upload', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Upload failed.');
      }

      applyDatasetPayload({
        columns: data.columns || [],
        columnMappings: data.columnMappings || {},
        validatedColumns: data.validatedColumns,
        filename: data.filename,
        rowCount: data.rowCount,
        validated: false,
        columnCount: data.columns?.length,
        droppedRowCount: data.droppedRowCount,
        outputColumns: data.outputColumns,
        sourceFormat: data.sourceFormat,
      });
    } catch (e) {
      error = e instanceof Error ? e.message : 'Upload failed.';
    } finally {
      uploading = false;
    }
  }

  function setMapping(roleKey: string, sourceColumn: string) {
    columnMappings = {
      ...columnMappings,
      [roleKey]: sourceColumn || null,
    };

    const role = roles.find((entry) => entry.key === roleKey);
    if (sourceColumn && role && (role.required || role.recommended)) {
      validateColumns = new Set([...validateColumns, sourceColumn]);
    }
  }

  function toggleValidateColumn(columnName: string, checked: boolean) {
    validateColumns = new Set(validateColumns);
    if (checked) {
      validateColumns.add(columnName);
    } else {
      validateColumns.delete(columnName);
    }
  }

  async function validateDataset() {
    cleaning = true;
    error = null;

    try {
      const response = await fetch('/api/gis/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          column_mappings: columnMappings,
          validate_columns: [...validateColumns],
          drop_incomplete_rows: dropIncompleteRows,
        }),
      });
      const data = await response.json();
      validationIssues = data.validation?.issues || [];
      incompleteRowCount = data.validation?.incomplete_row_count ?? 0;

      if (data.dataset) {
        applyDatasetPayload({
          columns: data.dataset.columns || [],
          columnMappings: data.dataset.columnMappings,
          validatedColumns: data.dataset.validatedColumns,
          filename: data.dataset.filename,
          rowCount: data.dataset.rowCount,
          validated: data.dataset.validated,
          columnCount: data.dataset.columns?.length,
          droppedRowCount: data.validation?.dropped_row_count ?? data.dataset.droppedRowCount,
          outputColumns: data.dataset.outputColumns,
          sourceFormat: data.dataset.sourceFormat,
        });
      }

      const semanticCols = data.semanticFieldCols || {};
      semanticFieldsStore.setConfigMeta({
        buildingIdCol: semanticCols.Building_ID_col || columnMappings.building_id || undefined,
        numFloorsCol: semanticCols.Num_Floors_col || columnMappings.num_floors || undefined,
      });
    } catch (e) {
      error = 'Validation failed.';
    } finally {
      cleaning = false;
    }
  }

  async function downloadCleanedDataset() {
    try {
      const response = await fetch('/api/gis/export');
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Export failed.');
      }
      await downloadFromResponse(response, 'buildings-cleaned.geojson');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Export failed.';
    }
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>GIS Cleaning</h1>
    <p class="subtitle">Upload your building data, match its columns to the model's inputs, and check for missing values.</p>
  </div>

  <div class="workflow-content">
    <div class="panel">
      <h2>1. Upload GIS data</h2>
      <p class="help">CSV or GeoJSON, one row per building.</p>
      <div class="upload-row">
        <input
          type="file"
          accept=".csv,.geojson,.json"
          onchange={(event) => {
            const target = event.currentTarget as HTMLInputElement;
            selectedFile = target.files?.[0] || null;
          }}
        />
        <button type="button" onclick={uploadFile} disabled={uploading || !selectedFile}>
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </div>
      {#if $gisDataset}
        <div class="summary">
          <strong>{$gisDataset.filename}</strong>
          <span>{$gisDataset.rowCount} rows</span>
          <span>{$gisDataset.columnCount} columns</span>
          <span class:validated={$gisDataset.validated} class:pending={!$gisDataset.validated}>
            <span aria-hidden="true">{$gisDataset.validated ? '✓' : '!'}</span>
            {$gisDataset.validated ? 'Validated' : 'Not validated yet'}
          </span>
        </div>
      {/if}
    </div>

    {#if columns.length > 0}
      <div class="panel">
        <h2>2. Match columns</h2>
        <p class="help">Pick which of your columns holds each model input. Only required inputs must be matched.</p>
        <div class="mapping-grid">
          {#each roles as role}
            <label>
              <span class="role-label">
                {role.label}
                {#if role.required}
                  <span class="tag required">required</span>
                {:else if role.recommended}
                  <span class="tag recommended">recommended</span>
                {/if}
              </span>
              {#if role.description}
                <span class="role-description">{role.description}</span>
              {/if}
              <select
                value={columnMappings[role.key] || ''}
                onchange={(event) =>
                  setMapping(role.key, (event.currentTarget as HTMLSelectElement).value)}
              >
                <option value="">Not mapped</option>
                {#each columns as column}
                  <option value={column.name}>{column.name}</option>
                {/each}
              </select>
            </label>
          {/each}
        </div>
      </div>

      <div class="panel">
        <h2>3. Check for missing values</h2>
        <details open={columns.length <= 12}>
          <summary>Columns to check ({validateColumns.size} of {columns.length} selected)</summary>
        <div class="validation-grid">
          {#each columns as column}
            <label class="checkbox-row">
              <input
                type="checkbox"
                checked={validateColumns.has(column.name)}
                onchange={(event) =>
                  toggleValidateColumn(column.name, (event.currentTarget as HTMLInputElement).checked)}
              />
              <span>{column.name}</span>
              <span class="null-count">{column.nullCount ?? 0} empty</span>
            </label>
          {/each}
        </div>
        </details>
      </div>

      <div class="panel">
        <h2>4. Validate</h2>
        <label class="checkbox-row drop-option">
          <input type="checkbox" bind:checked={dropIncompleteRows} />
          <span>Drop rows with missing values in the checked columns</span>
        </label>
        {#if incompleteRowCount > 0 && !dropIncompleteRows}
          <p class="help">{incompleteRowCount} rows have missing values. Tick the box above to drop them.</p>
        {/if}
        <div class="action-row">
          <button type="button" onclick={validateDataset} disabled={cleaning}>
            {cleaning ? 'Validating…' : dropIncompleteRows ? 'Validate & drop rows' : 'Validate'}
          </button>
          {#if $gisDataset?.validated}
            <button type="button" class="secondary" onclick={downloadCleanedDataset}>
              Download cleaned {sourceFormat === 'csv' ? 'CSV' : 'GeoJSON'}
            </button>
          {/if}
        </div>
        {#if droppedRowCount > 0}
          <p class="success">Dropped {droppedRowCount} incomplete rows. {$gisDataset?.rowCount ?? 0} rows remain.</p>
        {/if}
        {#if outputColumns.length > 0 && $gisDataset?.validated}
          <p class="help">Export includes: {outputColumns.join(', ')}</p>
        {/if}
        {#if validationIssues.length > 0}
          <ul class="issues">
            {#each validationIssues as issue}
              <li>{issue}</li>
            {/each}
          </ul>
        {/if}
      </div>

      {#if $gisDataset?.validated}
        <WorkflowGuide
          title="GIS data is ready"
          message="Next, turn its columns into the building categories the model uses."
          actionLabel="Go to Semantic Fields"
          actionWorkflow="semantic-fields"
        />
      {/if}
    {:else}
      <WorkflowGuide
        title="Start with GIS data"
        message="Upload a CSV or GeoJSON of your buildings above to begin."
      />
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
  .help {
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

  .panel {
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    background: var(--surface);
  }

  .panel h2 {
    margin: 0 0 8px;
    font-size: 18px;
  }

  .upload-row {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-top: 12px;
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

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .summary {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-top: 16px;
    color: var(--text-2);
    font-size: 14px;
  }

  .validated {
    color: var(--ok-text);
    font-weight: 600;
  }

  .pending {
    color: var(--warn-text);
    font-weight: 600;
  }

  .mapping-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
    color: var(--text-2);
  }

  .role-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: var(--text);
  }

  .role-description {
    color: var(--text-muted);
    font-size: 12px;
  }

  .tag {
    font-size: 10px;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 999px;
    font-weight: 700;
  }

  .tag.required {
    background: var(--err-bg);
    color: var(--err-text);
  }

  .tag.recommended {
    background: var(--warn-bg);
    color: var(--warn-text);
  }

  select,
  input[type='file'] {
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    padding: 8px 10px;
    font: inherit;
  }

  details summary {
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-2);
    margin-bottom: 10px;
  }

  .validation-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 8px;
  }

  .checkbox-row {
    flex-direction: row;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }

  .null-count {
    margin-left: auto;
    color: var(--text-muted);
    font-size: 12px;
  }

  .issues {
    margin: 16px 0 0;
    padding-left: 18px;
    color: var(--warn-text);
  }

  .error {
    color: var(--err-text);
  }

  .action-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 12px;
  }

  .secondary {
    background: var(--surface);
    color: var(--accent);
    border: 1px solid var(--accent);
  }

  .drop-option {
    margin-bottom: 12px;
  }

  .success {
    margin-top: 12px;
    color: var(--ok-text);
    font-size: 14px;
  }
</style>
