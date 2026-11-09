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
  import Icon from '../components/Icon.svelte';
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
  /** "Columns to check" starts open for short files, then stays as the user leaves it. */
  let columnsOpen = false;
  let columnsOpenSet = false;
  $: if (!columnsOpenSet && columns.length) {
    columnsOpen = columns.length <= 12;
    columnsOpenSet = true;
  }
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
    const formData = new FormData();
    formData.append('file', selectedFile);
    await loadDataset(() => fetch('/api/gis/upload', { method: 'POST', body: formData }));
  }

  /** The bundled mock GIS: globi's 100-building tutorial stock. */
  function useSample() {
    return loadDataset(() => fetch('/api/gis/sample', { method: 'POST' }));
  }

  async function loadDataset(request: () => Promise<Response>) {
    uploading = true;
    error = null;
    validationIssues = [];

    try {
      if (roles.length === 0) {
        await loadRoles();
      }

      const response = await request();
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
    <div class="panel" data-tour="gis-upload">
      <h2>Upload GIS data <Explain text={help.upload} tip /></h2>
      <Explain text={help.upload} />
      <div class="actions">
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
        <span class="hint">or</span>
        <button type="button" class="btn btn-secondary" onclick={useSample} disabled={uploading}>
          Use sample buildings (100)
        </button>
      </div>
      {#if $gisDataset}
        <div class="summary">
          <strong>{$gisDataset.filename}</strong>
          <span>{$gisDataset.rowCount} rows</span>
          <span>{$gisDataset.columnCount} columns</span>
          {#if $gisDataset.validated}
            <span class="status-ok"><Icon name="check" size={14} />Validated</span>
          {:else}
            <span class="status-warn"><Icon name="alert" size={14} />Not validated yet</span>
          {/if}
        </div>
      {/if}
    </div>

    {#if columns.length > 0}
      <div class="panel" data-tour="gis-match">
        <h2>Match columns <Explain text={help.match} tip /></h2>
        <Explain text={help.match} />
        <div class="field-grid">
          {#each roles as role}
            <label class="field">
              <span class="role-label">
                {role.label}
                {#if role.required}
                  <span class="tag tag-err">required</span>
                {:else if role.recommended}
                  <span class="tag tag-warn">recommended</span>
                {/if}
              </span>
              {#if role.description}
                <span class="field-hint">{role.description}</span>
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

      <div class="panel" data-tour="gis-missing">
        <h2>Check for missing values <Explain text={help.missing} tip /></h2>
        <Explain text={help.missing} />
        <details bind:open={columnsOpen}>
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
        <h2>Validate <Explain text={help.validate} tip /></h2>
        <Explain text={help.validate} />
        <label class="checkbox-row">
          <input type="checkbox" bind:checked={dropIncompleteRows} />
          <span>Drop rows with missing values in the checked columns</span>
        </label>
        {#if incompleteRowCount > 0 && !dropIncompleteRows}
          <p class="hint">{incompleteRowCount} rows have missing values. Tick the box above to drop them.</p>
        {/if}
        <div class="actions">
          <button type="button" class="btn" onclick={validateDataset} disabled={cleaning} data-tour="gis-validate">
            {cleaning ? 'Validating…' : dropIncompleteRows ? 'Validate & drop rows' : 'Validate'}
          </button>
          {#if $gisDataset?.validated}
            <button type="button" class="btn btn-secondary" onclick={downloadCleanedDataset}>
              Download cleaned {sourceFormat === 'csv' ? 'CSV' : 'GeoJSON'}
            </button>
          {/if}
        </div>
        {#if droppedRowCount > 0}
          <p class="status-ok"><Icon name="check" size={14} />Dropped {droppedRowCount} incomplete rows. {$gisDataset?.rowCount ?? 0} rows remain.</p>
        {/if}
        {#if outputColumns.length > 0 && $gisDataset?.validated}
          <p class="hint">Export includes: {outputColumns.join(', ')}</p>
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
  .summary {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .role-label {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }

  details summary {
    margin-bottom: var(--space-3);
    color: var(--text-2);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .validation-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: var(--space-1) var(--space-4);
  }

  .checkbox-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--control-h-sm);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .null-count {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
  }

  .issues {
    padding-left: var(--space-4);
    color: var(--warn-text);
    font-size: var(--text-sm);
  }
</style>
