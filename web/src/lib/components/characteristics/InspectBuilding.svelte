<script lang="ts">
  /**
   * One real building, traced through the model: the values its data gives it (and
   * which rule produced each), the values estimated for it as shares over many draws,
   * and the library record each model part resolves to. Uses the unsaved editor state,
   * so it answers "what would happen now".
   */
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { priorTreesStore } from '../../stores/priorTreesStore';
  import { componentMapStore } from '../../stores/componentMapStore';
  import { inspectBuilding, type BuildingTrace } from '../../api/priorTrees';
  import { MODEL_PARTS } from '../../utils/modelParts';
  import { formatPercent } from '../../utils/priorViz';
  import WeightBar from '../priorTrees/WeightBar.svelte';
  import Icon from '../Icon.svelte';

  let { onClose }: { onClose: () => void } = $props();

  let buildingId = $state('');
  let trace = $state<BuildingTrace | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);

  function partLabel(path: string): string {
    return MODEL_PARTS.find((part) => part.paths.includes(path))?.label ?? path;
  }

  async function run(id: string | null) {
    loading = true;
    error = null;
    try {
      trace = await inspectBuilding(
        $semanticFieldsStore.fields,
        $priorTreesStore.config,
        $componentMapStore.map,
        $semanticFieldsStore.buildingIdCol,
        id
      );
      buildingId = trace.buildingId ?? '';
    } catch (e) {
      trace = null;
      error = e instanceof Error ? e.message : 'Could not inspect that building.';
    } finally {
      loading = false;
    }
  }
</script>

<div class="panel inspect">
  <div class="header">
    <h2>Inspect a building</h2>
    <button type="button" class="btn btn-ghost btn-sm" onclick={onClose}>Close</button>
  </div>
  <form
    class="pick"
    onsubmit={(event) => {
      event.preventDefault();
      void run(buildingId.trim() || null);
    }}
  >
    <label class="field">
      <span>{$semanticFieldsStore.buildingIdCol}</span>
      <input bind:value={buildingId} placeholder="Building ID" />
    </label>
    <button type="submit" class="btn btn-sm" disabled={loading || !buildingId.trim()}>Inspect</button>
    <button type="button" class="btn btn-secondary btn-sm" disabled={loading} onclick={() => run(null)}>
      Random building
    </button>
  </form>

  {#if error}<p class="error" role="alert">{error}</p>{/if}

  {#if trace}
    <div class="columns">
      <section>
        <h3>From its data</h3>
        {#each trace.known as entry}
          <p>
            <strong>{entry.name}</strong> = {entry.value ?? '—'}
            <span class="hint">({entry.because})</span>
          </p>
        {:else}
          <p class="hint">No characteristics come from data yet.</p>
        {/each}
      </section>

      <section>
        <h3>Estimated, over {trace.n} draws</h3>
        <p class="hint">The spread is what the model doesn't know about this building.</p>
        {#each trace.estimated as entry}
          {@const distribution = Object.fromEntries(entry.shares.map((s) => [s.value ?? '—', s.share]))}
          <div class="estimate">
            <strong>{entry.name}</strong>
            <WeightBar {distribution} order={Object.keys(distribution)} />
          </div>
        {:else}
          <p class="hint">No estimates yet.</p>
        {/each}
      </section>
    </div>

    <section>
      <h3>Library records it uses</h3>
      {#if trace.parts.length === 0}
        <p class="hint">No model parts are connected yet.</p>
      {:else}
        <table class="data-table">
          <thead>
            <tr><th>Model part</th><th>Record</th><th class="num">Share of draws</th><th>In library</th></tr>
          </thead>
          <tbody>
            {#each trace.parts as part}
              {#each part.records as record, index}
                <tr>
                  <td>{index === 0 ? partLabel(part.path) : ''}</td>
                  <td><code>{record.name ?? `missing a value for ${part.sourceFields.join(' / ')}`}</code></td>
                  <td class="num">{formatPercent(record.share)}</td>
                  <td>
                    {#if record.exists === true}<span class="status-ok"><Icon name="check" size={14} />exists</span>
                    {:else if record.exists === false}<span class="status-err"><Icon name="x" size={14} />missing</span>
                    {:else}<span class="hint">unknown</span>{/if}
                  </td>
                </tr>
              {/each}
            {/each}
          </tbody>
        </table>
      {/if}
    </section>
  {/if}
</div>

<style>
  .inspect {
    gap: var(--space-4);
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .header h2,
  h3 {
    margin: 0;
  }

  h3 {
    font-size: var(--text-md);
    margin-bottom: var(--space-2);
  }

  .pick {
    display: flex;
    align-items: flex-end;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  .columns {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: var(--space-5);
  }

  p {
    margin: 0 0 var(--space-2);
    font-size: var(--text-sm);
  }

  .estimate {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-3);
    font-size: var(--text-sm);
  }
</style>
