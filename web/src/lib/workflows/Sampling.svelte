<script lang="ts">
  /**
   * Which buildings to simulate and how many draws of the estimated characteristics each gets.
   * Writing produces gis/buildings-sampled.geojson (one row per building × draw), which Model
   * Execution's batch files then point at. Works from the saved characteristics and estimates.
   */
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import Explain from '../components/Explain.svelte';
  import { fetchSamplingSettings, previewSampling, writeSampling, type SamplingSettings, type SamplingSummary } from '../api/sampling';
  import { gisDataset, navigateTo } from '../stores/projectStore';
  import { dirtyKinds } from '../stores/projectArtifacts';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { priorTreesStore } from '../stores/priorTreesStore';
  import { HELP } from '../help';
  const help = HELP.sampling;

  let settings: SamplingSettings | null = null;
  let summary: SamplingSummary | null = null;
  let written: SamplingSummary | null = null;
  let error: string | null = null;
  let writing = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  onMount(async () => {
    try {
      settings = await fetchSamplingSettings();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load the sampling settings.';
    }
  });

  $: fromData = $semanticFieldsStore.fields.filter((field) => field.type !== 'stochastic').map((field) => field.name);
  $: ready = Boolean($gisDataset?.validated) && $dirtyKinds.length === 0 && $semanticFieldsStore.fields.length > 0;
  $: if (settings && ready) schedulePreview(JSON.stringify(settings));

  function schedulePreview(_key: string) {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!settings) return;
      try {
        summary = await previewSampling($semanticFieldsStore.fields, $priorTreesStore.config, settings);
        error = null;
      } catch (e) {
        summary = null;
        error = e instanceof Error ? e.message : 'Preview failed.';
      }
    }, 300);
  }

  function toggleStratum(name: string) {
    if (!settings) return;
    const strata = settings.buildings.strata;
    settings.buildings.strata = strata.includes(name) ? strata.filter((s) => s !== name) : [...strata, name];
  }

  async function write() {
    if (!settings) return;
    writing = true;
    error = null;
    try {
      written = await writeSampling($semanticFieldsStore.fields, $priorTreesStore.config, settings);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to write the sample.';
    } finally {
      writing = false;
    }
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Sampling <Explain text={help.page} tip /></h1>
    <Explain text={help.page} />
  </div>

  <div class="workflow-content">
    {#if !$gisDataset?.validated}
      <WorkflowGuide title="Validate GIS data first" message="Sampling picks from your validated buildings." actionLabel="Go to GIS Cleaning" actionWorkflow="gis-cleaning" />
    {:else if $semanticFieldsStore.fields.length === 0 || $dirtyKinds.length > 0}
      <WorkflowGuide
        title="Save your building characteristics first"
        message="Sampling uses the saved characteristics and estimates, so the buildings it writes match the files globi reads."
        actionLabel="Go to Building Characteristics"
        actionWorkflow="characteristics"
      />
    {:else if settings}
      <div class="panel">
        <h2>Buildings <Explain text={help.buildings} tip /></h2>
        <Explain text={help.buildings} />
        <div class="modes" role="radiogroup" aria-label="Which buildings">
          <label><input type="radio" bind:group={settings.buildings.mode} value="all" /> All buildings ({$gisDataset.rowCount})</label>
          <label>
            <input type="radio" bind:group={settings.buildings.mode} value="random" /> A random
            <input type="number" min="1" bind:value={settings.buildings.n} disabled={settings.buildings.mode !== 'random'} aria-label="Number of buildings" />
          </label>
          <label>
            <input type="radio" bind:group={settings.buildings.mode} value="stratified" />
            <input type="number" min="1" bind:value={settings.buildings.per_stratum} disabled={settings.buildings.mode !== 'stratified'} aria-label="Buildings per combination" />
            per combination of
          </label>
        </div>
        {#if settings.buildings.mode === 'stratified'}
          <div class="chips">
            {#each fromData as name}
              <label class="chip"><input type="checkbox" checked={settings.buildings.strata.includes(name)} onchange={() => toggleStratum(name)} /> {name}</label>
            {:else}
              <span class="muted">Add a From my data characteristic to stratify by.</span>
            {/each}
          </div>
        {/if}
        <label class="inline">Seed <input type="number" min="0" step="1" bind:value={settings.seed} /></label>
      </div>

      <div class="panel">
        <h2>Estimates <Explain text={help.draws} tip /></h2>
        <Explain text={help.draws} />
        {#if summary && summary.estimated.length > 0}
          <label class="inline">Draws per building <input type="number" min="1" max="1000" bind:value={settings.draws} /></label>
          <p class="muted">Drawn each time: {summary.estimated.join(', ')}.</p>
        {:else}
          <p class="muted">No estimated characteristics, so each building is simulated once with its data values.</p>
        {/if}
      </div>

      <div class="panel">
        {#if summary}
          <p class="readout">
            <strong>{summary.buildings}</strong> buildings{#if summary.strata !== null} in {summary.strata} combinations{/if}
            × <strong>{summary.draws}</strong> draw{summary.draws === 1 ? '' : 's'} = <strong>{summary.simulations.toLocaleString()}</strong> simulations
          </p>
          {#if summary.skipped}<p class="muted">{summary.skipped} buildings left out: they lack a value an estimate depends on.</p>{/if}
        {/if}
        <div>
          <button type="button" class="btn" onclick={write} disabled={writing || !summary}>
            {writing ? 'Writing…' : 'Write sampled buildings'}
          </button>
        </div>
        {#if written}
          <p class="done">
            <span aria-hidden="true">✓</span> Wrote {written.rows} rows to <code>{written.path}</code>. Model Execution's batch files will run over it.
            <button type="button" class="btn btn-link" onclick={() => navigateTo('model-execution')}>Go to Model Execution</button>
          </p>
        {/if}
      </div>
    {/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </div>
</section>

<style>
  .workflow-content { max-width: 860px; }
  .modes { display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
  .modes label, .inline { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; }
  input[type='number'] { width: 80px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px; }
  .readout { margin: 0; font-size: 15px; }
  .muted { color: var(--text-muted); font-size: 13px; margin: 0; }
  .done { color: var(--ok-text); font-size: 13px; margin: 0; font-weight: 600; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
</style>
