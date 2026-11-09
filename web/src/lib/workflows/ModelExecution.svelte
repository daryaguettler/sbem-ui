<script lang="ts">
  /** The readiness checklist, globi's run files generated from the saved project, and an editor snapshot export. */
  import { onMount } from 'svelte';
  import {
    HATCHET_URL,
    fetchGlobiFilesStatus,
    fetchLatestRuns,
    fetchRunScenarios,
    generateGlobiFiles,
    resumeRun,
    runBuilding,
    runSample,
    type BuildingGeometry,
    type BuildingRunResult,
    type EndUses,
    type GeneratedGlobiFiles,
    type GlobiFilesStatus,
    type SampleRunResult,
  } from '../api/globiFiles';
  import BarChart from '../components/BarChart.svelte';
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

  /** Runs from this page: the form's building, or a random sample of the stock. */
  let running: 'building' | 'sample' | null = null;
  let stage = '';
  let elapsed = 0;
  let runError: string | null = null;
  let runErrorKind: 'building' | 'sample' | null = null;
  let buildingRun: BuildingRunResult | null = null;
  let sampleRun: SampleRunResult | null = null;
  let sampleSize = 10;
  let runScenarios: string[] = [];
  let chosenScenarios: string[] = [];
  // shortcut: batch submission still fails in globi main (allocate.py's schedule variability); set true once it runs
  const BATCH_RUNS = false;
  /** The embedded Hatchet dashboard loads only while its section is open. */
  let showHatchet = false;

  async function loadScenarios() {
    runScenarios = await fetchRunScenarios().catch(() => []);
    chosenScenarios = chosenScenarios.filter((s) => runScenarios.includes(s));
    if (chosenScenarios.length === 0) chosenScenarios = [...runScenarios];
  }

  /** Follow a run, timing it from `startedAt` (a run resumed after a reload keeps its clock). */
  async function track<T>(kind: 'building' | 'sample', run: (onStage: (s: string) => void) => Promise<T>, startedAt?: string): Promise<T | null> {
    running = kind;
    runError = null;
    stage = 'Starting…';
    const start = startedAt ? Date.parse(startedAt) : Date.now();
    elapsed = Math.max(0, Math.round((Date.now() - start) / 1000));
    const timer = setInterval(() => (elapsed = Math.round((Date.now() - start) / 1000)), 1000);
    try {
      return await run((s) => (stage = s || stage));
    } catch (e) {
      runError = e instanceof Error ? e.message : 'The run failed.';
      runErrorKind = kind;
      return null;
    } finally {
      clearInterval(timer);
      running = null;
    }
  }

  async function runThisBuilding() {
    buildingRun = null;
    await generate();
    if (!result) return; // generate shows its own error
    buildingRun = await track('building', runBuilding);
  }

  async function runTheSample() {
    sampleRun = null;
    showHatchet = true;
    sampleRun = await track('sample', (onStage) => runSample(Math.max(1, Math.round(sampleSize)), chosenScenarios, onStage));
  }

  /** Show the project's last runs: results of finished ones, and keep following a live one. */
  async function resumeRuns() {
    const latest = await fetchLatestRuns().catch(() => null);
    if (!latest) return;
    if (latest.building?.status === 'done') buildingRun = latest.building.result;
    if (latest.sample?.status === 'done') sampleRun = latest.sample.result;
    for (const [kind, job] of [['building', latest.building], ['sample', latest.sample]] as const) {
      if (job && (job.status === 'failed' || job.status === 'interrupted')) {
        runError = job.error;
        runErrorKind = kind;
      }
    }
    if (latest.sample?.status === 'running') {
      const job = latest.sample;
      showHatchet = true;
      sampleRun = (await track('sample', (onStage) => resumeRun(job, onStage), job.startedAt)) ?? sampleRun;
    } else if (latest.building?.status === 'running') {
      const job = latest.building;
      buildingRun = (await track('building', (onStage) => resumeRun(job, onStage), job.startedAt)) ?? buildingRun;
    }
  }

  const total = (uses: EndUses) => Object.values(uses).reduce((sum, v) => sum + v, 0);
  const minutes = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  $: sampleScenarios = sampleRun ? Object.keys(sampleRun.scenarios) : [];
  $: sampleEndUses = sampleRun ? [...new Set(sampleScenarios.flatMap((s) => Object.keys(sampleRun!.scenarios[s].mean_kwh_m2)))] : [];
  $: sampleTotals = sampleScenarios.map((s) => total(sampleRun!.scenarios[s].mean_kwh_m2));
  $: sampleBuildings = sampleRun && sampleScenarios.length ? sampleRun.scenarios[sampleScenarios[0]].buildings : [];
  $: totalsById = Object.fromEntries(
    sampleScenarios.map((s) => [s, Object.fromEntries(sampleRun!.scenarios[s].buildings.map((b) => [b.building_id, total(b.end_uses_kwh_m2)]))])
  );

  onMount(async () => {
    void runLibraryCheck();
    void loadScenarios();
    void resumeRuns();
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
      void loadScenarios();
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
  <div class="layout">
  <div class="form">
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
        <h3>Example building (one test run)</h3>
        <p class="hint">
          One building you describe here, for a quick check that the model runs. It is only used for <code>building.yml</code>
          (<code>globi simulate</code>) and <strong>Run this example</strong>. Batch and sample runs ignore it: each of your
          buildings uses its own values and size from the saved buildings.
        </p>
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
          <button type="button" class="btn btn-secondary" onclick={runThisBuilding} disabled={running !== null || generating || !status.componentMapSaved}>
            {running === 'building' ? 'Running…' : 'Run this example'}
          </button>
        </div>
        <p class="hint">Run this example generates the files, then simulates the example with EnergyPlus on this machine (about 10 s).</p>
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
      {#if running === 'building'}<p class="hint" role="status">{stage} · {minutes(elapsed)}</p>{/if}
      {#if runError && runErrorKind === 'building'}<p class="error" role="alert">{runError}</p>{/if}
    </div>

    <div class="panel">
      <h2>Run a sample of your buildings</h2>
      <p class="hint">
        Simulates the same random buildings under each scenario on globi's local engine. Start it first in the globi folder:
        <code>make hatchet-token</code>, then <code>make engine</code>.
      </p>
      {#if runScenarios.length === 0}
        <p class="hint">Generate globi files with saved buildings first (Sampling → Write sampled buildings).</p>
      {:else}
        <div class="sample-form">
          <label class="field">Buildings<input type="number" min="1" step="1" bind:value={sampleSize} /></label>
          <fieldset class="field">
            <legend>Scenarios</legend>
            <div class="checks-row">
              {#each runScenarios as scenario}
                <label><input type="checkbox" value={scenario} bind:group={chosenScenarios} /> {scenario}</label>
              {/each}
            </div>
          </fieldset>
        </div>
        <div class="actions">
          <button type="button" class="btn" onclick={runTheSample} disabled={!BATCH_RUNS || running !== null || chosenScenarios.length === 0}>
            {running === 'sample' ? 'Running…' : `Run ${sampleSize} buildings × ${chosenScenarios.length} scenario${chosenScenarios.length === 1 ? '' : 's'}`}
            {#if !BATCH_RUNS}<span class="tag tag-warn">in progress</span>{/if}
          </button>
        </div>
        {#if !BATCH_RUNS}
          <p class="hint">Batch runs are still being connected to GloBI. You can set up the sample here; the run itself isn't available yet.</p>
        {/if}
      {/if}

      {#if running === 'sample'}<p class="hint" role="status">{stage} · {minutes(elapsed)}</p>{/if}
      {#if runError && runErrorKind === 'sample'}<p class="error" role="alert">{runError}</p>{/if}

      <details class="hatchet" bind:open={showHatchet}>
        <summary>Jobs in Hatchet (live: one task per building, with its logs)</summary>
        <p class="hint">
          Sign in with <code>admin@example.com</code> / <code>Admin123!!</code> (globi's local default), then open <strong>Runs</strong>.
          <a href={HATCHET_URL} target="_blank" rel="noopener noreferrer">Open in a new tab</a> ·
          <button type="button" class="btn btn-link" onclick={() => navigateTo('simulations')}>Full page</button>
        </p>
        {#if showHatchet}<iframe title="Hatchet dashboard" src={HATCHET_URL}></iframe>{/if}
      </details>

    </div>

    <div class="panel">
      <h2>Export <Explain text={help.export} tip /></h2>
      <Explain text={help.export} />
      <div class="actions"><button type="button" class="btn btn-secondary" onclick={exportManifest} disabled={!$allArtifactsReady}>Download editor snapshot</button></div>
    </div>
  </div>
  <aside class="results">
    {#if buildingRun}
      {@const rows = Object.entries(buildingRun.end_uses_kwh_m2)}
      {@const peakRows = Object.entries(buildingRun.peak_kw_m2).filter(([, v]) => v > 0)}
      <div class="panel">
        <h2>Example building <span class="unit">kWh/m² · total {total(buildingRun.end_uses_kwh_m2).toFixed(1)}</span></h2>
        <p class="hint">{Object.entries(buildingRun.context).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>
        <BarChart {rows} unit="kWh/m²" />
        <details>
          <summary>Show table</summary>
          <table class="data-table">
            <thead><tr><th>End use</th><th class="num">kWh/m²</th></tr></thead>
            <tbody>
              {#each rows as [name, value]}<tr><td>{name}</td><td class="num">{value.toFixed(1)}</td></tr>{/each}
              <tr class="total"><td>Total</td><td class="num">{total(buildingRun.end_uses_kwh_m2).toFixed(1)}</td></tr>
            </tbody>
          </table>
        </details>
      </div>
      {#if peakRows.length}
        <div class="panel">
          <h2>Peak loads <span class="unit">kW/m²</span></h2>
          <BarChart rows={peakRows} unit="kW/m²" decimals={3} />
        </div>
      {/if}
      <p class="hint">Files in <code>{buildingRun.output_dir}</code></p>
    {/if}
    {#if sampleRun}
      <div class="panel">
        <h2>Sample of {sampleRun.buildings} buildings <span class="unit">kWh/m², floor-area weighted</span></h2>
        <BarChart rows={sampleScenarios.map((s, i) => [s, sampleTotals[i]])} unit="kWh/m²" />
        <table class="data-table">
          <thead>
            <tr><th>End use</th>{#each sampleScenarios as s}<th class="num">{s}</th>{/each}</tr>
          </thead>
          <tbody>
            {#each sampleEndUses as use}
              <tr>
                <td>{use}</td>
                {#each sampleScenarios as s}<td class="num">{(sampleRun.scenarios[s].mean_kwh_m2[use] ?? 0).toFixed(1)}</td>{/each}
              </tr>
            {/each}
            <tr class="total">
              <td>Total</td>
              {#each sampleTotals as t, i}
                <td class="num">
                  {t.toFixed(1)}
                  {#if i > 0 && sampleTotals[0] > 0}<span class="hint">({(((t - sampleTotals[0]) / sampleTotals[0]) * 100).toFixed(0)}%)</span>{/if}
                </td>
              {/each}
            </tr>
          </tbody>
        </table>
        <details>
          <summary>Each building (total kWh/m²)</summary>
          <table class="data-table">
            <thead>
              <tr><th>Building</th><th>Characteristics</th>{#each sampleScenarios as s}<th class="num">{s}</th>{/each}</tr>
            </thead>
            <tbody>
              {#each sampleBuildings as b (b.building_id)}
                <tr>
                  <td><code>{b.building_id.slice(0, 8)}</code></td>
                  <td>{Object.entries(b.values).filter(([k]) => k !== 'Scenario').map(([, v]) => v).join(' · ')}</td>
                  {#each sampleScenarios as s}<td class="num">{totalsById[s]?.[b.building_id]?.toFixed(1) ?? '–'}</td>{/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </details>
        <p class="hint">Run files and downloaded results (with an .xlsx per scenario) in <code>{sampleRun.run_dir}</code></p>
      </div>
    {/if}
    {#if !buildingRun && !sampleRun}<p class="hint">Results appear here after a run.</p>{/if}
  </aside>
  </div>
  </div>
</section>

<style>
  .layout { display: grid; grid-template-columns: minmax(0, 860px) minmax(320px, 1fr); gap: var(--space-6); align-items: start; }
  .form, .results { display: flex; flex-direction: column; gap: var(--space-6); }
  .results { position: sticky; top: var(--space-6); }
  @media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } .results { position: static; } }
  .unit { font-size: var(--text-sm); font-weight: 400; color: var(--text-muted); }
  summary { cursor: pointer; font-size: var(--text-sm); color: var(--text-muted); }
  .hatchet iframe { width: 100%; height: 70vh; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
  .checks { list-style: none; display: flex; flex-direction: column; gap: var(--space-2); font-size: var(--text-sm); }
  .checks li { display: flex; align-items: baseline; gap: var(--space-3); }
  .checks .tag { min-width: 64px; }
  .check-text { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .status-ok, .status-warn { font-size: var(--text-sm); }
  .sample-form { display: flex; gap: var(--space-4); align-items: flex-end; flex-wrap: wrap; }
  .sample-form input[type='number'] { width: 8em; }
  fieldset.field { border: none; padding: 0; margin: 0; }
  .checks-row { display: flex; gap: var(--space-3); flex-wrap: wrap; font-size: var(--text-sm); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .total td { font-weight: 600; }
  details { font-size: var(--text-sm); }
  pre { padding: var(--space-3); background: var(--surface-2); border-radius: var(--radius); font-size: var(--text-xs); white-space: pre-wrap; word-break: break-all; }
</style>
