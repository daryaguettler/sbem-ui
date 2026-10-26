<script lang="ts">
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import { helpMode } from '../stores/helpMode';
  import { gisDataset } from '../stores/projectStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import type { GlobiColumnRole, GisColumnMappings } from '../types/gis';
  import type { GISColumn } from '../types/semanticFields';
  import { downloadFromResponse } from '../utils/download';
  import Explain from '../components/Explain.svelte';
  import Select from '../components/Select.svelte';
  import { HELP } from '../help';
  const help = HELP.gis;

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
    <h1>GIS Cleaning <Explain text={help.page} tip /></h1>
    <Explain text={help.page} />
  </div>

  <div class="workflow-content">
    <div class="panel">
      <h2>1. Upload GIS data <Explain text={help.upload} tip /></h2>
      <Explain text={help.upload} />
      <div class="upload-row">
        <input
          type="file"
          accept=".csv,.geojson,.json"
          onchange={(event) => {
            const target = event.currentTarget as HTMLInputElement;
            selectedFile = target.files?.[0] || null;
          }}
        />
        <button type="button" class="btn" onclick={uploadFile} disabled={uploading || !selectedFile}>
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
        <h2>2. Match columns <Explain text={help.match} tip /></h2>
        <Explain text={help.match} />
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
              <Select
                value={columnMappings[role.key] || ''}
                options={[
                  { value: '', label: 'Not mapped' },
                  ...columns.map((column) => ({ value: column.name, label: column.name })),
                ]}
                onChange={(value) => setMapping(role.key, value)}
              />
            </label>
          {/each}
        </div>
      </div>

      <div class="panel">
        <h2>3. Check for missing values <Explain text={help.missing} tip /></h2>
        <Explain text={help.missing} />
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
        <h2>4. Validate <Explain text={help.validate} tip /></h2>
        <Explain text={help.validate} />
        <label class="checkbox-row drop-option">
          <input type="checkbox" bind:checked={dropIncompleteRows} />
          <span>Drop rows with missing values in the checked columns</span>
        </label>
        {#if incompleteRowCount > 0 && !dropIncompleteRows}
          <p class="help">{incompleteRowCount} rows have missing values. Tick the box above to drop them.</p>
        {/if}
        <div class="action-row">
          <button type="button" class="btn" onclick={validateDataset} disabled={cleaning}>
            {cleaning ? 'Validating…' : dropIncompleteRows ? 'Validate & drop rows' : 'Validate'}
          </button>
          {#if $gisDataset?.validated}
            <button type="button" class="btn btn-secondary" onclick={downloadCleanedDataset}>
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
          message="Next, describe the building characteristics the model uses, from your columns or as estimates."
          actionLabel="Go to Building Characteristics"
          actionWorkflow="characteristics"
        />
      {/if}
    {:else if $helpMode === 'explain'}
      <WorkflowGuide
        title="Start with GIS data"
        message="Upload a CSV or GeoJSON of your buildings above to begin."
      />
    {/if}

    {#if error}
      <p class="error" role="alert">{error}</p>
    {/if}
  </div>
</section>

<style>
  .help {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .upload-row {
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }

  .summary {
    display: flex;
    gap: var(--space-4);
    flex-wrap: wrap;
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
    font-size: 11px;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
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

  input[type='file'] {
    font: inherit;
    font-size: var(--text-sm);
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
    border-radius: var(--radius);
  }

  .null-count {
    margin-left: auto;
    color: var(--text-muted);
    font-size: 12px;
  }

  .issues {
    padding-left: 18px;
    color: var(--warn-text);
  }

  .action-row {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .success {
    color: var(--ok-text);
    font-size: var(--text-sm);
  }
</style>
