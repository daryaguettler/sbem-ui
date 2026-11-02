<script lang="ts">
  /**
   * One building as a flat model: every parameter typed in, no semantic fields or
   * component library. Saved to the project's flat-building.yml and simulated by globi.
   */
  import { onMount } from 'svelte';
  import {
    FlatModelError,
    fetchFlatModel,
    runFlatModel,
    saveFlatModel,
    type FlatModelField,
    type FlatModelResult,
  } from '../api/flatModel';

  let fields: FlatModelField[] = [];
  let values: Record<string, unknown> = {};
  let file = '';
  let fieldErrors: Record<string, string> = {};
  let error: string | null = null;
  let running = false;
  let result: FlatModelResult | null = null;

  onMount(async () => {
    try {
      load(await fetchFlatModel());
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not load the building.';
    }
  });

  function load(form: { file: string; fields: FlatModelField[] }) {
    file = form.file;
    fields = form.fields;
    values = Object.fromEntries(fields.map((f) => [f.name, f.value]));
  }

  async function run() {
    running = true;
    error = null;
    fieldErrors = {};
    result = null;
    try {
      load(await saveFlatModel(values));
      result = await runFlatModel();
    } catch (e) {
      error = e instanceof Error ? e.message : 'The run failed.';
      if (e instanceof FlatModelError) fieldErrors = e.fields;
    } finally {
      running = false;
    }
  }

  $: groups = [...new Set(fields.map((f) => f.group))];
  $: endUses = result ? Object.entries(result.end_uses_kwh_m2) : [];
  $: total = endUses.reduce((sum, [, v]) => sum + v, 0);
  $: peaks = result ? Object.entries(result.peak_kw_m2).filter(([, v]) => v > 0) : [];
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Single Building</h1>
    <p class="subtitle">Type in every parameter of one building and simulate it. Saved to <code>{file || 'flat-building.yml'}</code>.</p>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error">{error}</p>{/if}

    {#if result}
      <div class="panel">
        <h2>Results</h2>
        <table>
          <thead><tr><th>End use</th><th>kWh/m²</th></tr></thead>
          <tbody>
            {#each endUses as [name, value]}
              <tr><td>{name}</td><td>{value.toFixed(1)}</td></tr>
            {/each}
            <tr class="total"><td>Total</td><td>{total.toFixed(1)}</td></tr>
          </tbody>
        </table>
        <p class="muted">
          Peak: {peaks.map(([name, v]) => `${name} ${v.toFixed(3)} kW/m²`).join(' · ')} · files in <code>{result.output_dir}</code>
        </p>
      </div>
    {/if}

    {#if fields.length}
      <div class="panel">
        <div class="head">
          <h2>Building</h2>
          <button type="button" onclick={run} disabled={running}>{running ? 'Running…' : 'Save and run'}</button>
        </div>
        {#if running}<p class="muted">The first run builds globi's Docker image, which takes several minutes.</p>{/if}

        {#each groups as group}
          <h3>{group}</h3>
          <div class="grid">
            {#each fields.filter((f) => f.group === group) as field (field.name)}
              <label class:invalid={fieldErrors[field.name]}>
                <span class="name">{field.name}</span>
                {#if field.type === 'choice'}
                  <select bind:value={values[field.name]}>
                    {#each field.options ?? [] as option}<option value={option}>{option}</option>{/each}
                  </select>
                {:else if field.type === 'text'}
                  <input type="text" bind:value={values[field.name]} />
                {:else}
                  <input
                    type="number"
                    step={field.type === 'integer' ? 1 : 'any'}
                    min={field.min}
                    max={field.max}
                    bind:value={values[field.name]}
                  />
                {/if}
                <span class="hint">{fieldErrors[field.name] ?? field.hint}</span>
              </label>
            {/each}
          </div>
        {/each}
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
  .panel h3 { margin: 6px 0 0; font-size: 13px; color: var(--text-muted); font-weight: 600; }
  .head { display: flex; justify-content: space-between; align-items: center; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px 16px; }
  label { display: flex; flex-direction: column; gap: 3px; font-size: 13px; }
  .name { font-weight: 500; }
  .hint { color: var(--text-muted); font-size: 11px; min-height: 13px; }
  .invalid .hint { color: var(--err-text); }
  .invalid input, .invalid select { border-color: var(--err-border); }
  input, select { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; background: var(--bg); color: var(--text); }
  table { border-collapse: collapse; font-size: 13px; width: 100%; max-width: 360px; }
  th { text-align: left; color: var(--text-muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--border); }
  td { padding: 6px 8px; border-bottom: 1px solid var(--surface-3); }
  .total td { font-weight: 600; }
  button { border: none; border-radius: 8px; background: var(--accent); color: var(--on-accent); padding: 8px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .muted { color: var(--text-muted); font-size: 13px; margin: 0; }
  .error { color: var(--err-text); font-size: 13px; margin: 0; }
</style>
