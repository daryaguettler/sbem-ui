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
  import { allArtifactsReady, gisDataset, navigateTo, readinessChecks, runLibraryCheck } from '../stores/projectStore';
  import { componentMapStore } from '../stores/componentMapStore';
  import { priorTreesStore } from '../stores/priorTreesStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { workspaceStore } from '../stores/workspaceStore';
  import { tutorialMarks } from '../stores/tutorial';
  import { downloadText } from '../utils/download';
  import Explain from '../components/Explain.svelte';
  import Icon from '../components/Icon.svelte';
  import Select from '../components/Select.svelte';
  import { HELP } from '../help';
  const help = HELP.modelExecution;

  let status: GlobiFilesStatus | null = null;
  let context: Record<string, string> = {};
  let weather = '';
  let geometry: BuildingGeometry = { length: 20, width: 15, num_floors: 2, f2f_height: 3.5, wwr: 0.3 };
  let generating = false;
  let result: GeneratedGlobiFiles | null = null;
  let error: string | null = null;

  onMount(async () => {
    void runLibraryCheck();
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
      tutorialMarks.update((marks) => ({ ...marks, runFiles: true }));
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
    <h1>Model Execution <Explain text={help.page} tip /></h1>
    <Explain text={help.page} />
  </div>

  <div class="workflow-content">
    <div class="panel" data-tour="exec-readiness">
      <h2>Readiness <Explain text={help.readiness} tip /></h2>
      <Explain text={help.readiness} />
      <ul class="checks">
        {#each $readinessChecks as check}
          <li>
            <span class="tag {check.ready ? 'tag-ok' : 'tag-warn'}">
              <Icon name={check.ready ? 'check' : 'alert'} size={12} />{check.ready ? 'Ready' : 'To do'}
            </span>
            <span class="check-text">
              <strong>{check.label}</strong>
              <span class="hint">{check.detail}</span>
            </span>
            {#if !check.ready}<button type="button" class="btn btn-link" onclick={() => navigateTo(check.workflow)}>Go to step</button>{/if}
          </li>
        {/each}
      </ul>
    </div>

    <div class="panel">
      <h2>GloBI run files <Explain text={help.globiFiles} tip /></h2>
      <Explain text={help.globiFiles} />
      {#if status && status.fields.length === 0}
        <p class="hint">Save your building characteristics first.</p>
        <div class="actions"><button type="button" class="btn btn-link" onclick={() => navigateTo('characteristics')}>Go to Building Characteristics</button></div>
      {:else if status}
        <h3>Building for <code>globi simulate</code></h3>
        <div class="field-grid" style="--field-min: 160px" data-tour="exec-building">
          {#each status.fields as field}
            <div class="field">
              <span>{field.name}</span>
              <Select
                value={context[field.name]}
                options={field.options.map((option) => ({ value: String(option), label: String(option) }))}
                onChange={(value) => (context[field.name] = value)}
                ariaLabel={field.name}
              />
            </div>
          {/each}
          <label class="field">Length (m)<input type="number" min="3" bind:value={geometry.length} /></label>
          <label class="field">Width (m)<input type="number" min="3" bind:value={geometry.width} /></label>
          <label class="field">Floors<input type="number" min="1" step="1" bind:value={geometry.num_floors} /></label>
          <label class="field">Floor-to-floor (m)<input type="number" min="0" step="0.1" bind:value={geometry.f2f_height} /></label>
          <label class="field">Window-to-wall ratio<input type="number" min="0" max="1" step="0.05" bind:value={geometry.wwr} /></label>
        </div>
        <label class="field">
          Weather file (.zip with .epw and .ddy): a project path or a URL
          <input type="text" list="weather-files" bind:value={weather} placeholder="weather/….zip or https://…" />
          <datalist id="weather-files">{#each status.weather as file}<option value={file}></option>{/each}</datalist>
        </label>
        <p class="hint">
          {status.gisFile
            ? `Batch files will run over ${status.gisFile}.`
            : 'No buildings saved yet (Sampling, or Building Characteristics → GloBI files → Save to project), so only building.yml will be written.'}
        </p>
        <div class="actions">
          <button type="button" class="btn" onclick={generate} disabled={generating || !status.componentMapSaved} data-tour="globi-generate">
            {generating ? 'Generating…' : 'Generate globi files'}
          </button>
        </div>
        {#if !status.componentMapSaved}<p class="hint">Save the model parts first (Component Map → Save).</p>{/if}
      {/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if result}
        <p class="status-ok"><Icon name="check" size={14} /><span>Wrote {result.written.join(', ')}</span></p>
        {#each result.warnings as warning}<p class="status-warn"><Icon name="alert" size={14} /><span>{warning}</span></p>{/each}
        <p class="hint" data-tour="exec-commands">Run from <code>{result.cwd}</code>:</p>
        <pre data-tour="exec-commands">{result.commands.simulate}</pre>
        {#if result.commands.batch}
          <p class="hint">Batch run (needs globi's local stack first: <code>make hatchet-token</code>, <code>make engine</code>):</p>
          <pre>{result.commands.batch}</pre>
        {/if}
      {/if}
    </div>

    <div class="panel">
      <h2>Export <Explain text={help.export} tip /></h2>
      <Explain text={help.export} />
      <div class="actions"><button type="button" class="btn btn-secondary" onclick={exportManifest} disabled={!$allArtifactsReady}>Download editor snapshot</button></div>
    </div>
  </div>
</section>

<style>
  .workflow-content { max-width: 860px; }
  .checks { list-style: none; display: flex; flex-direction: column; gap: var(--space-2); font-size: var(--text-sm); }
  .checks li { display: flex; align-items: baseline; gap: var(--space-3); }
  .checks .tag { min-width: 64px; }
  .check-text { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .status-ok, .status-warn { font-size: var(--text-sm); }
  pre { padding: var(--space-3); background: var(--surface-2); border-radius: var(--radius); font-size: var(--text-xs); white-space: pre-wrap; word-break: break-all; }
</style>
