<script lang="ts">
  /**
   * How the surrogate is trained and how inference is split: strata (training.yml's
   * `norway_training`), the simulation budget, and the required inference partition
   * field (inference.yml). Candidate columns and the estimate come from the runner.
   */
  import { onMount } from 'svelte';
  import RunnerNotice from '../components/RunnerNotice.svelte';
  import HelpTip from '../components/HelpTip.svelte';
  import {
    fetchRunnerStatus,
    fetchSampling,
    runJob,
    saveSampling,
    type SamplingSettings,
  } from '../api/runner';

  interface Column {
    name: string;
    n_values: number | null;
    numeric: boolean;
  }
  interface SamplingInfo {
    n_buildings: number;
    columns: Column[];
    n_strata: number | null;
    estimate: { simulations: number; wall_hours: number; usd: number } | null;
  }

  let settings: SamplingSettings | null = null;
  let info: SamplingInfo | null = null;
  let runnerAvailable = false;
  let loadingInfo = false;
  let saving = false;
  let dirty = false;
  let error: string | null = null;
  let addStratum = '';
  let perIter = '';

  $: columns = info?.columns ?? [];
  $: available = columns.filter((c) => !settings?.strata_fields.includes(c.name));
  $: partitionChoices = columns.filter((c) => c.name !== 'weather_station');

  onMount(async () => {
    try {
      settings = await fetchSampling();
      perIter = toList(settings.n_per_iter);
      runnerAvailable = (await fetchRunnerStatus()).available;
      if (runnerAvailable) await refreshInfo();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load the sampling settings.';
    }
  });

  function toList(value: number | number[] | null): string {
    return value === null ? '' : Array.isArray(value) ? value.join(', ') : String(value);
  }

  async function refreshInfo() {
    loadingInfo = true;
    try {
      info = await runJob<SamplingInfo>('sampling');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not read the GIS.';
    } finally {
      loadingInfo = false;
    }
  }

  function changed() {
    settings = settings;
    dirty = true;
  }

  function add() {
    if (!settings || !addStratum) return;
    settings.strata_fields = [...settings.strata_fields, addStratum];
    addStratum = '';
    changed();
  }

  function remove(field: string) {
    if (!settings) return;
    settings.strata_fields = settings.strata_fields.filter((f) => f !== field);
    changed();
  }

  function count(field: string): string {
    const n = columns.find((c) => c.name === field)?.n_values;
    return n ? ` · ${n}` : '';
  }

  async function save() {
    if (!settings) return;
    saving = true;
    error = null;
    try {
      const iters = perIter.split(',').map((v) => Number(v.trim())).filter((v) => v > 0);
      if (iters.length === 0) throw new Error('Simulations per iteration must be a number.');
      settings = await saveSampling({ ...settings, n_per_iter: iters });
      dirty = false;
      if (runnerAvailable) await refreshInfo();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to save.';
    } finally {
      saving = false;
    }
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <div>
      <h1>Sampling</h1>
      <p class="intro">How many buildings to simulate for training, and how to split the stock for prediction.</p>
      <p class="subtitle">
        {#if loadingInfo}
          Estimating…
        {:else if info}
          {info.n_buildings.toLocaleString()} buildings
          {#if info.n_strata} · {info.n_strata} strata{/if}
          {#if info.estimate} · ≤ {info.estimate.simulations.toLocaleString()} simulations · ~${info.estimate.usd.toFixed(0)}{/if}
        {/if}
      </p>
    </div>
    <button type="button" onclick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</button>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error">{error}</p>{/if}
    {#if settings && !runnerAvailable}
      <RunnerNotice feature="Listing GIS columns for strata and estimating simulation count and cost" />
    {/if}
    {#if settings}
      <div class="panel">
        <h2>Training</h2>
        <div class="row">
          <span class="label">Strata <HelpTip text="GIS columns that split the stock into groups (strata), e.g. weather station × typology. Every stratum gets simulations in the first round, and training only stops once each stratum is accurate enough." /></span>
          <div class="chips">
            {#each settings.strata_fields as field}
              <span class="chip">{field}<span class="muted">{count(field)}</span>
                <button type="button" class="chip-x" title="Remove" onclick={() => remove(field)}>×</button>
              </span>
            {/each}
            {#if columns.length}
              <select bind:value={addStratum} onchange={add} aria-label="Add stratum">
                <option value="">+ Add column</option>
                {#each available as column}
                  <option value={column.name}>{column.name}{column.n_values ? ` (${column.n_values})` : ''}</option>
                {/each}
              </select>
            {:else}
              <input
                type="text"
                bind:value={addStratum}
                placeholder="GIS column name"
                aria-label="Add stratum"
                onkeydown={(event) => event.key === 'Enter' && add()}
              />
              <button type="button" class="secondary" onclick={add} disabled={!addStratum}>+ Add</button>
            {/if}
          </div>
        </div>

        <div class="row">
          <span class="label">Min per stratum <HelpTip text="Simulations each stratum gets in the first round. The first round is raised to at least strata × this number." /></span>
          <input type="number" min="1" bind:value={settings.min_per_stratum} oninput={changed} />
        </div>
        <div class="row">
          <span class="label">Simulations per round <HelpTip text="Buildings simulated in each training round. One number for every round, or a comma-separated list per round (the last value repeats)." /></span>
          <input type="text" bind:value={perIter} oninput={changed} placeholder="5000, 5000" />
        </div>
        <div class="row">
          <span class="label">Max rounds <HelpTip text="Training stops after this many rounds even if some strata haven't converged." /></span>
          <input type="number" min="1" bind:value={settings.max_iters} oninput={changed} />
        </div>
        <div class="row">
          <span class="label">Context per stratum <HelpTip text="Most buildings kept per stratum in the training context. Simulated buildings are drawn from this subsample, so this limits its size." /></span>
          <input type="number" min="1" bind:value={settings.context_per_stratum} oninput={changed} />
        </div>

        <h2>Prediction</h2>
        <div class="row">
          <span class="label">Split stock by <span class="required" aria-label="required">*</span> <HelpTip text="GIS column that splits the stock into prediction jobs and output files, e.g. municipality. Required." /></span>
          {#if partitionChoices.length}
            <select bind:value={settings.partition_field} onchange={changed}>
              <option value={null}>Choose a GIS column…</option>
              {#each partitionChoices as column}
                <option value={column.name}>{column.name}{column.n_values ? ` (${column.n_values})` : ''}</option>
              {/each}
            </select>
          {:else}
            <input type="text" bind:value={settings.partition_field} oninput={changed} placeholder="GIS column, e.g. municipality" />
          {/if}
        </div>
        <div class="row">
          <span class="label">Draws per building <HelpTip text="How many times each building's unknown fields (heating system etc.) are sampled from the priors. More draws give smoother results but take longer." /></span>
          <input type="number" min="1" bind:value={settings.n_samples} oninput={changed} />
        </div>
      </div>
    {/if}
  </div>
</section>

<style>
  .workflow { display: flex; flex-direction: column; height: 100%; }
  .workflow-header {
    padding: 24px 32px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .workflow-header h1 { margin: 0 0 4px; font-size: 24px; }
  .subtitle { margin: 0; color: var(--text-muted); font-size: 13px; }
  .workflow-content { padding: 32px; max-width: 760px; display: flex; flex-direction: column; gap: 16px; }
  .panel { border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .row { display: flex; align-items: center; gap: 16px; font-size: 14px; }
  .intro { margin: 0 0 2px; color: var(--text-muted); font-size: 14px; }
  .panel h2 { margin: 6px 0 0; font-size: 14px; color: var(--text); }
  .label { width: 190px; color: var(--text-2); flex-shrink: 0; }
  .required { color: var(--err-text); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chip { display: inline-flex; align-items: center; gap: 2px; background: var(--surface-3); border-radius: 999px; padding: 4px 6px 4px 12px; font-size: 13px; }
  .chip-x { border: none; background: transparent; color: var(--text-faint); cursor: pointer; padding: 0 4px; font-size: 14px; }
  .chip-x:hover { color: var(--text); }
  input, select { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; background: var(--surface); }
  input[type='text'], select { min-width: 240px; }
  input[type='number'] { width: 110px; }
  button { border: none; border-radius: 8px; background: var(--accent); color: var(--on-accent); padding: 8px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
  button.secondary { background: var(--surface); color: var(--text-2); border: 1px solid var(--border-strong); padding: 5px 10px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .muted { color: var(--text-muted); }
  .error { color: var(--err-text); font-size: 13px; margin: 0; }
</style>
