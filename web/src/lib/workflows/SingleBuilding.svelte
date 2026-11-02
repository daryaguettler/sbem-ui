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
  import Select from '../components/Select.svelte';

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
    <p class="hint">Type in every parameter of one building and simulate it. Saved to <code>{file || 'flat-building.yml'}</code>.</p>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error">{error}</p>{/if}

    {#if result}
      <div class="panel">
        <h2>Results</h2>
        <table class="data-table">
          <thead><tr><th>End use</th><th class="num">kWh/m²</th></tr></thead>
          <tbody>
            {#each endUses as [name, value]}
              <tr><td>{name}</td><td class="num">{value.toFixed(1)}</td></tr>
            {/each}
            <tr class="total"><td>Total</td><td class="num">{total.toFixed(1)}</td></tr>
          </tbody>
        </table>
        <p class="hint">
          Peak: {peaks.map(([name, v]) => `${name} ${v.toFixed(3)} kW/m²`).join(' · ')} · files in <code>{result.output_dir}</code>
        </p>
      </div>
    {/if}

    {#if fields.length}
      <div class="panel">
        <div class="head">
          <h2>Building</h2>
          <button type="button" class="btn" onclick={run} disabled={running}>{running ? 'Running…' : 'Save and run'}</button>
        </div>
        {#if running}<p class="hint">The first run builds globi's Docker image, which takes several minutes.</p>{/if}

        {#each groups as group}
          <h3>{group}</h3>
          <div class="field-grid" style="--field-min: 220px">
            {#each fields.filter((f) => f.group === group) as field (field.name)}
              <label class="field" class:invalid={fieldErrors[field.name]}>
                <span class="name">{field.name}</span>
                <span class="field-hint">{fieldErrors[field.name] ?? field.hint}</span>
                {#if field.type === 'choice'}
                  <Select
                    value={String(values[field.name] ?? '')}
                    options={(field.options ?? []).map((option) => ({ value: option, label: option }))}
                    onChange={(value) => (values[field.name] = value)}
                    ariaLabel={field.name}
                  />
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
              </label>
            {/each}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</section>

<style>
  .workflow-content { max-width: 860px; }
  .data-table { max-width: 360px; }
  .total td { font-weight: 600; }
  .head { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); }
  .name { font-weight: 500; }
  .invalid .field-hint { color: var(--err-text); }
  .invalid input, .invalid :global(.ui-select-trigger) { border-color: var(--err-border); }
</style>
