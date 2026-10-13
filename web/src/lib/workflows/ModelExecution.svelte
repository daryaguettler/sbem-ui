<script lang="ts">
  /**
   * With a runner repo (project.json `"runner"`): validate every input and launch a small
   * local test run (EnergyPlus on this machine; capped). Without one: the readiness
   * checklist and manifest export.
   */
  import { onMount } from 'svelte';
  import RunnerNotice from '../components/RunnerNotice.svelte';
  import { fetchSavedArtifact } from '../api/artifacts';
  import { MAX_TEST_BUILDINGS, fetchRunnerStatus, runJob } from '../api/runner';
  import { allArtifactsReady, gisDataset, navigateTo, readinessChecks } from '../stores/projectStore';
  import { componentMapStore } from '../stores/componentMapStore';
  import { priorTreesStore } from '../stores/priorTreesStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { downloadText } from '../utils/download';

  interface Check {
    name: string;
    level: 'ok' | 'warn' | 'error';
    message: string;
  }
  interface ScenarioRow {
    scenario: string;
    n_draws: number;
    eui_total_mean: number | null;
    savings_mean: number | null;
    share_changed: number | null;
  }
  interface TestRun {
    out_dir: string;
    n_buildings: number;
    n_simulations: number;
    n_failed: number;
    failures: string[];
    by_scenario: ScenarioRow[];
  }

  let runnerAvailable = false;
  let checks: Check[] | null = null;
  let validating = false;
  let testing = false;
  let n = 10;
  let packages: string[] = [];
  let selected: string[] = [];
  let run: TestRun | null = null;
  let error: string | null = null;

  onMount(async () => {
    try {
      runnerAvailable = (await fetchRunnerStatus()).available;
      const saved = await fetchSavedArtifact('retrofits');
      packages = ((saved.content?.packages as { name: string }[]) ?? []).map((p) => p.name);
      selected = [...packages];
    } catch {
      runnerAvailable = false;
    }
  });

  async function validate() {
    validating = true;
    error = null;
    try {
      checks = (await runJob<{ checks: Check[] }>('validate')).checks;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Validation failed.';
    } finally {
      validating = false;
    }
  }

  async function testRun() {
    testing = true;
    error = null;
    run = null;
    try {
      const size = Math.min(Math.max(1, Math.round(n)), MAX_TEST_BUILDINGS);
      run = await runJob<TestRun>('test-run', { n: size, samples: 1, packages: selected });
    } catch (e) {
      error = e instanceof Error ? e.message : 'Test run failed.';
    } finally {
      testing = false;
    }
  }

  function toggle(name: string) {
    selected = selected.includes(name) ? selected.filter((p) => p !== name) : [...selected, name];
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

  const pct = (v: number | null) => (v === null ? '' : `${Math.round(v * 100)}%`);

  // Status is an icon + word, not just a colored dot.
  const LEVEL = {
    ok: { icon: '✓', word: 'OK' },
    warn: { icon: '!', word: 'Warning' },
    error: { icon: '✕', word: 'Error' },
  } as const;

  // An empty package list means "all packages" to the runner, so require a choice.
  $: noPackageSelected = packages.length > 0 && selected.length === 0;
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Model Execution</h1>
    <p class="subtitle">{runnerAvailable ? 'Check readiness, validate inputs and run a small local test.' : 'Check readiness and export a snapshot.'}</p>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error">{error}</p>{/if}

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

    {#if runnerAvailable}
      <div class="panel">
        <div class="head">
          <h2>Inputs</h2>
          <button type="button" onclick={validate} disabled={validating}>{validating ? 'Checking…' : 'Validate'}</button>
        </div>
        {#if checks}
          <ul class="checks">
            {#each checks as check}
              <li>
                <span class="badge {check.level}"><span aria-hidden="true">{LEVEL[check.level].icon}</span> {LEVEL[check.level].word}</span>
                <strong>{check.name}</strong><span class="muted">{check.message}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="panel">
        <div class="head">
          <h2>Test run</h2>
          <div class="controls">
            <label><input type="number" min="1" max={MAX_TEST_BUILDINGS} bind:value={n} /> buildings</label>
            <button
              type="button"
              onclick={testRun}
              disabled={testing || noPackageSelected}
              title={noPackageSelected ? 'Select at least one retrofit package' : undefined}
            >
              {testing ? 'Running…' : 'Run locally'}
            </button>
          </div>
        </div>
        {#if packages.length}
          <div class="packages">
            {#each packages as name}
              <label><input type="checkbox" checked={selected.includes(name)} onchange={() => toggle(name)} /> {name}</label>
            {/each}
          </div>
        {/if}
        {#if run}
          <table>
            <thead><tr><th>Scenario</th><th>EUI (kWh/m²)</th><th>Savings</th><th>Buildings changed</th></tr></thead>
            <tbody>
              {#each run.by_scenario as row}
                <tr>
                  <td>{row.scenario}</td>
                  <td>{row.eui_total_mean?.toFixed(1) ?? '–'}</td>
                  <td>{pct(row.savings_mean)}</td>
                  <td>{pct(row.share_changed)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          <p class="muted">
            {run.n_buildings} buildings · {run.n_simulations - run.n_failed}/{run.n_simulations} simulations ok
            {#if run.failures.length} · {run.failures[0]}{/if}
          </p>
        {/if}
      </div>
    {:else}
      <RunnerNotice feature="Validating inputs against globi and running a local test" />
      <div class="panel">
        <h2>Export</h2>
        <div><button type="button" onclick={exportManifest} disabled={!$allArtifactsReady}>Download editor snapshot</button></div>
        <p class="muted">
          A JSON snapshot of this project's editors, for sharing or archiving. It is not a globi
          <code>manifest.yml</code> and can't be passed to <code>globi submit</code>.
        </p>
      </div>
    {/if}
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
  .head { display: flex; justify-content: space-between; align-items: center; }
  .controls { display: flex; align-items: center; gap: 12px; font-size: 13px; }
  .controls input { width: 64px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
  .packages { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; }
  .checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
  .checks li { display: flex; align-items: flex-start; gap: 10px; }
  .checks strong { min-width: 120px; font-weight: 600; }
  .badge { display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0; min-width: 76px; padding: 1px 8px; border-radius: 999px; border: 1px solid; font-size: 11px; font-weight: 700; }
  .badge.ok { color: var(--ok-text); background: var(--ok-bg); border-color: var(--ok-border); }
  .badge.warn { color: var(--warn-text); background: var(--warn-bg); border-color: var(--warn-border); }
  .badge.error { color: var(--err-text); background: var(--err-bg); border-color: var(--err-border); }
  .check-text { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  table { border-collapse: collapse; font-size: 13px; width: 100%; }
  th { text-align: left; color: var(--text-muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--border); }
  td { padding: 6px 8px; border-bottom: 1px solid var(--surface-3); }
  button { border: none; border-radius: 8px; background: var(--accent); color: var(--on-accent); padding: 8px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .link { background: transparent; color: var(--accent); padding: 0; font-weight: 500; white-space: nowrap; }
  .muted { color: var(--text-muted); font-size: 13px; margin: 0; }
  .error { color: var(--err-text); font-size: 13px; margin: 0; }
</style>
