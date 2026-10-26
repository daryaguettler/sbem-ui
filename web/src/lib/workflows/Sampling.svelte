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
  import Explain from '../components/Explain.svelte';
  import Select from '../components/Select.svelte';
  import { HELP } from '../help';
  const help = HELP.sampling;

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
      <h1>Sampling <Explain text={help.page} tip /></h1>
      <Explain text={help.page} />
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
    <button type="button" class="btn" onclick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</button>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if settings && !runnerAvailable}
      <RunnerNotice feature="Listing GIS columns for strata and estimating simulation count and cost" />
    {/if}
    {#if settings}
      <div class="panel">
        <h2>Training <Explain text={help.training} tip /></h2>
        <Explain text={help.training} />
        <div class="row">
          <span class="label">Strata <HelpTip text="GIS columns that split the stock into groups (strata), e.g. weather station × typology. Every stratum gets simulations in the first round, and training only stops once each stratum is accurate enough." /></span>
          <div class="chips">
            {#each settings.strata_fields as field}
              <span class="chip">{field}<span class="muted">{count(field)}</span>
                <button type="button" class="chip-x" title="Remove" onclick={() => remove(field)}>×</button>
              </span>
            {/each}
            {#if columns.length}
              <span class="pick">
                <Select
                  value=""
                  options={available.map((column) => ({
                    value: column.name,
                    label: `${column.name}${column.n_values ? ` (${column.n_values})` : ''}`,
                  }))}
                  placeholder="+ Add column"
                  ariaLabel="Add stratum"
                  onChange={(value) => {
                    addStratum = value;
                    add();
                  }}
                />
              </span>
            {:else}
              <input
                type="text"
                bind:value={addStratum}
                placeholder="GIS column name"
                aria-label="Add stratum"
                onkeydown={(event) => event.key === 'Enter' && add()}
              />
              <button type="button" class="btn btn-secondary btn-sm" onclick={add} disabled={!addStratum}>+ Add</button>
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

        <h2>Prediction <Explain text={help.prediction} tip /></h2>
        <Explain text={help.prediction} />
        <div class="row">
          <span class="label">Split stock by <span class="required" aria-label="required">*</span> <HelpTip text="GIS column that splits the stock into prediction jobs and output files, e.g. municipality. Required." /></span>
          {#if partitionChoices.length}
            <span class="pick">
              <Select
                value={settings.partition_field ?? ''}
                options={partitionChoices.map((column) => ({
                  value: column.name,
                  label: `${column.name}${column.n_values ? ` (${column.n_values})` : ''}`,
                }))}
                placeholder="Choose a GIS column…"
                ariaLabel="Partition field"
                onChange={(value) => {
                  if (!settings) return;
                  settings.partition_field = value || null;
                  changed();
                }}
              />
            </span>
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
  .workflow-header { flex-direction: row; justify-content: space-between; align-items: center; }
  .subtitle { margin: 0; color: var(--text-muted); font-size: 13px; }
  .workflow-content { max-width: 760px; }
  .row { display: flex; align-items: center; gap: 16px; font-size: 14px; }
  .label { width: 190px; color: var(--text-2); flex-shrink: 0; }
  .required { color: var(--err-text); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chip { display: inline-flex; align-items: center; gap: 2px; background: var(--surface-3); border-radius: var(--radius-sm); padding: 4px 6px 4px 12px; font-size: 13px; }
  .chip-x { border: none; background: transparent; color: var(--text-faint); cursor: pointer; padding: 0 4px; font-size: 14px; }
  .chip-x:hover { color: var(--text); }
  input[type='text'], .pick { min-width: 240px; }
  .pick { display: inline-block; }
  input[type='number'] { width: 110px; }
  .muted { color: var(--text-muted); }
</style>
