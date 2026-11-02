<script lang="ts">
  /** The readiness checklist, globi's run files generated from the saved project, and an editor snapshot export. */
  import { onMount } from 'svelte';
  import {
    fetchGlobiFilesStatus,
    generateGlobiFiles,
    type BuildingGeometry,
    type GeneratedGlobiFiles,
    type GlobiFilesStatus,
  } from '../api/globiFiles';
  import { allArtifactsReady, gisDataset, navigateTo, readinessChecks } from '../stores/projectStore';
  import { componentMapStore } from '../stores/componentMapStore';
  import { priorTreesStore } from '../stores/priorTreesStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { workspaceStore } from '../stores/workspaceStore';
  import { downloadText } from '../utils/download';

  let status: GlobiFilesStatus | null = null;
  let context: Record<string, string> = {};
  let weather = '';
  let geometry: BuildingGeometry = { length: 20, width: 15, num_floors: 2, f2f_height: 3.5, wwr: 0.3 };
  let generating = false;
  let result: GeneratedGlobiFiles | null = null;
  let error: string | null = null;

  onMount(async () => {
    try {
      status = await fetchGlobiFilesStatus();
      context = Object.fromEntries(status.fields.map((field) => [field.name, String(field.options[0] ?? '')]));
      weather = status.weather[0] ?? '';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to read the project.';
    }
  });

  async function generate() {
    generating = true;
    error = null;
    result = null;
    try {
      result = await generateGlobiFiles({
        name: $workspaceStore.workspace?.name ?? 'sbem-ui',
        epwzip_file: weather.trim(),
        context,
        building: geometry,
      });
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to generate globi files.';
    } finally {
      generating = false;
    }
  }

  function exportManifest() {
    const manifest = {
      name: 'SBEM UI editor snapshot',
      version: '0.1.0',
      status: $allArtifactsReady ? 'ready_for_export' : 'incomplete',
      artifacts: {
        gis: $gisDataset,
        semantic_fields: semanticFieldsStore.toExportPayload($semanticFieldsStore),
        component_map: $componentMapStore.map,
        prior_trees: $priorTreesStore.config,
      },
    };
    downloadText(JSON.stringify(manifest, null, 2), 'sbem-ui-snapshot.json', 'application/json');
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Model Execution</h1>
    <p class="subtitle">Check readiness, generate globi's run files and export a snapshot.</p>
  </div>

  <div class="workflow-content">
    <div class="panel">
      <h2>Readiness</h2>
      <ul class="checks">
        {#each $readinessChecks as check}
          <li>
            <span class="badge {check.ready ? 'ok' : 'warn'}">
              <span aria-hidden="true">{check.ready ? '✓' : '!'}</span> {check.ready ? 'Ready' : 'To do'}
            </span>
            <span class="check-text">
              <strong>{check.label}</strong>
              <span class="muted">{check.detail}</span>
            </span>
            {#if !check.ready}<button type="button" class="link" onclick={() => navigateTo(check.workflow)}>Go to step</button>{/if}
          </li>
        {/each}
      </ul>
    </div>

    <div class="panel">
      <h2>globi files</h2>
      <p class="muted">
        Written into the project from the <em>saved</em> semantic fields, component map, library and GIS:
        <code>building.yml</code> for one building (<code>globi simulate</code>), plus <code>manifest.yml</code>,
        <code>artifacts.yml</code> and <code>gis-preprocessor.yml</code> for a batch run over the saved GIS.
      </p>
      {#if status && status.fields.length === 0}
        <p class="muted">Save semantic fields first.</p>
        <div><button type="button" class="link" onclick={() => navigateTo('semantic-fields')}>Go to Semantic Fields</button></div>
      {:else if status}
        <h3>One building</h3>
        <div class="form-grid">
          {#each status.fields as field}
            <label>
              {field.name}
              <select bind:value={context[field.name]}>
                {#each field.options as option}<option value={String(option)}>{option}</option>{/each}
              </select>
            </label>
          {/each}
          <label>Length (m)<input type="number" min="3" bind:value={geometry.length} /></label>
          <label>Width (m)<input type="number" min="3" bind:value={geometry.width} /></label>
          <label>Floors<input type="number" min="1" step="1" bind:value={geometry.num_floors} /></label>
          <label>Floor-to-floor (m)<input type="number" min="0" step="0.1" bind:value={geometry.f2f_height} /></label>
          <label>Window-to-wall ratio<input type="number" min="0" max="1" step="0.05" bind:value={geometry.wwr} /></label>
        </div>
        <label class="wide">
          Weather file (.zip with .epw and .ddy): a project path or a URL
          <input type="text" list="weather-files" bind:value={weather} placeholder="weather/….zip or https://…" />
          <datalist id="weather-files">{#each status.weather as file}<option value={file}></option>{/each}</datalist>
        </label>
        <p class="muted">
          {status.gisFile
            ? `Batch files will run over ${status.gisFile}.`
            : 'No GIS saved yet (Semantic Fields → Save GIS to project), so only building.yml will be written.'}
        </p>
        <div>
          <button type="button" onclick={generate} disabled={generating || !status.componentMapSaved}>
            {generating ? 'Generating…' : 'Generate globi files'}
          </button>
        </div>
        {#if !status.componentMapSaved}<p class="muted">Save the component map first.</p>{/if}
      {/if}
      {#if error}<p class="error">{error}</p>{/if}
      {#if result}
        <p class="done"><span aria-hidden="true">✓</span> Wrote {result.written.join(', ')}</p>
        {#each result.warnings as warning}<p class="warning"><span aria-hidden="true">!</span> {warning}</p>{/each}
        <p class="muted">Run from <code>{result.cwd}</code>:</p>
        <pre>{result.commands.simulate}</pre>
        {#if result.commands.batch}
          <p class="muted">Batch run (needs globi's local stack first: <code>make hatchet-token</code>, <code>make engine</code>):</p>
          <pre>{result.commands.batch}</pre>
        {/if}
      {/if}
    </div>

    <div class="panel">
      <h2>Export</h2>
      <div><button type="button" onclick={exportManifest} disabled={!$allArtifactsReady}>Download editor snapshot</button></div>
      <p class="muted">
        A JSON snapshot of this project's editors, for sharing or archiving. It is not a globi
        <code>manifest.yml</code> and can't be passed to <code>globi submit</code>.
      </p>
    </div>
  </div>
</section>

<style>
  .workflow { display: flex; flex-direction: column; height: 100%; }
  .workflow-header { padding: 24px 32px; border-bottom: 1px solid var(--border); }
  .workflow-header h1 { margin: 0 0 4px; font-size: 24px; }
  .subtitle { margin: 0; color: var(--text-muted); font-size: 13px; }
  .workflow-content { padding: 32px; max-width: 860px; display: flex; flex-direction: column; gap: 20px; }
  .panel { border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .panel h2 { margin: 0; font-size: 15px; }
  .panel h3 { margin: 0; font-size: 13px; }
  .checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
  .checks li { display: flex; align-items: flex-start; gap: 10px; }
  .checks strong { min-width: 120px; font-weight: 600; }
  .badge { display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0; min-width: 76px; padding: 1px 8px; border-radius: 999px; border: 1px solid; font-size: 11px; font-weight: 700; }
  .badge.ok { color: var(--ok-text); background: var(--ok-bg); border-color: var(--ok-border); }
  .badge.warn { color: var(--warn-text); background: var(--warn-bg); border-color: var(--warn-border); }
  .check-text { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 600; color: var(--text-muted); }
  input, select { font: inherit; font-weight: 400; font-size: 13px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
  pre { margin: 0; padding: 10px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
  button { border: none; border-radius: 8px; background: var(--accent); color: var(--on-accent); padding: 8px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .link { background: transparent; color: var(--accent); padding: 0; font-weight: 500; white-space: nowrap; }
  .muted { color: var(--text-muted); font-size: 13px; margin: 0; }
  .error { color: var(--err-text); font-size: 13px; margin: 0; }
  .done { color: var(--ok-text); font-size: 13px; margin: 0; font-weight: 600; }
  .warning { color: var(--warn-text); font-size: 13px; margin: 0; }
</style>
