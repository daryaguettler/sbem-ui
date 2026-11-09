<script lang="ts">
  /**
   * One building characteristic, as four questions: what values it takes, how we know
   * it per building, what it changes in the model, and (later) the records it needs.
   * Edits go straight to the underlying stores; changes that touch more than one file
   * (rename, remove, switching how it is known) go through stores/characteristics.
   */
  import type { FieldPreview, GISColumn, SemanticField } from '../../types/semanticFields';
  import type { CharacteristicView, HowKnown } from '../../utils/characteristics';
  import { dependentsOf } from '../../utils/characteristics';
  import { parseOptionsText, withOptions } from '../../utils/semanticFieldRules';
  import { removeCharacteristic, renameCharacteristic, setHowKnown } from '../../stores/characteristics';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { priorTreesStore } from '../../stores/priorTreesStore';
  import SemanticFieldAssist from '../SemanticFieldAssist.svelte';
  import DataRuleEditor from './DataRuleEditor.svelte';
  import EstimateEditor from './EstimateEditor.svelte';
  import ModelPartsChecklist from './ModelPartsChecklist.svelte';
  import { partRulesStore } from '../../stores/partRulesStore';
  import { navigateTo } from '../../stores/projectStore';
  import { partsUsing } from '../../utils/partRules';
  import { partLabel } from '../../utils/modelParts';
  import Explain from '../Explain.svelte';
  import { HELP } from '../../help';
  const help = HELP.characteristics;

  let {
    view,
    gisColumns,
    apiFields,
    preview,
    previewLoading,
    onFieldChange,
    fieldOrder,
    onShowConnections,
  }: {
    view: CharacteristicView;
    gisColumns: GISColumn[];
    apiFields: unknown[];
    preview: FieldPreview | null;
    previewLoading: boolean;
    /** Write a field edit to the store and refresh the preview. */
    onFieldChange: (next: SemanticField) => void;
    /** Characteristic names in list order. */
    fieldOrder: string[];
    /** Open the All connections view at a component path. */
    onShowConnections: (path: string) => void;
  } = $props();

  const field = $derived(view.field);

  function rename(value: string) {
    const name = value.trim();
    // An untitled field has nothing pointing at it yet, so there is nothing else to rename.
    if (!field.name) semanticFieldsStore.updateField(field.id, { name });
    else renameCharacteristic(field.name, name);
  }

  function changeHowKnown(mode: HowKnown) {
    if (mode === view.howKnown) return;
    const rule = field.transformationRule;
    const loses =
      mode === 'estimate'
        ? rule?.sourceColumn
          ? 'its rule on your GIS data'
          : null
        : view.hasEstimate
          ? 'its estimate'
          : null;
    if (loses && !confirm(`Switching "${field.name || 'this characteristic'}" removes ${loses}. Continue?`)) return;
    setHowKnown(field.name, mode);
  }

  function remove() {
    const dependents = dependentsOf($priorTreesStore.config, field.name);
    const warning = dependents.length
      ? ` The estimates for ${dependents.join(', ')} depend on it and will need re-estimating.`
      : '';
    if (!confirm(`Remove "${field.name || 'Untitled'}" and the model parts it chooses?${warning}`)) return;
    // Untitled fields can't be found by name; nothing else refers to them yet.
    if (!field.name) semanticFieldsStore.removeField(field.id);
    else removeCharacteristic(field.name);
  }

</script>

<article class="panel card">
  <header class="card-header">
    <label class="name">
      <span class="visually-hidden">Name</span>
      <input
        value={field.name}
        placeholder="Name, e.g. Heating"
        onchange={(event) => rename((event.currentTarget as HTMLInputElement).value)}
      />
    </label>
    <button type="button" class="btn btn-secondary btn-sm" onclick={remove}>Remove</button>
  </header>

  {#if view.issues.length > 0}
    <ul class="callout callout-err issues" aria-label="To fix">
      {#each view.issues as issue}
        <li>{issue}</li>
      {/each}
    </ul>
  {/if}

  <section data-tour="char-values">
    <h3>What values can it take? <Explain text={help.values} tip /></h3>
    <Explain text={help.values} />
    {#key field.id}
      <SemanticFieldAssist {field} {apiFields} onApply={(draft) => onFieldChange({ ...draft, id: field.id })} />
    {/key}
    <label class="field">
      Values (comma-separated)
      <input
        value={field.options.join(', ')}
        placeholder="e.g. SFH, MFH"
        onchange={(event) =>
          onFieldChange(
            withOptions(field, parseOptionsText((event.currentTarget as HTMLInputElement).value), gisColumns)
          )}
      />
    </label>
  </section>

  <section data-tour="char-known">
    <h3>How do we know it for each building? <Explain text={help.howKnown} tip /></h3>
    <Explain text={help.howKnown} />
    <div class="choice" role="radiogroup" aria-label="How we know it">
      <button
        type="button"
        role="radio"
        aria-checked={view.howKnown === 'data'}
        class:selected={view.howKnown === 'data'}
        onclick={() => changeHowKnown('data')}
      >
        <strong>From my data</strong>
        <span>A rule on a GIS column</span>
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={view.howKnown === 'estimate'}
        class:selected={view.howKnown === 'estimate'}
        onclick={() => changeHowKnown('estimate')}
      >
        <strong>Estimate it</strong>
        <span>Drawn from odds you set</span>
      </button>
    </div>

    {#if view.howKnown === 'data'}
      <DataRuleEditor {field} {gisColumns} onChange={onFieldChange} />
      {#if preview}
        {@const stats = preview.stats}
        {@const most = Math.max(1, ...Object.values(stats.counts), stats.unmapped_count)}
        <Explain text={help.spread} />
        <ul class="spread" class:stale={previewLoading} aria-label="Buildings per value">
          {#each Object.entries(stats.counts) as [value, count] (value)}
            <li>
              <span class="label">{value}</span>
              <span class="bar" style:width="{(count / most) * 100}%"></span>
              <span class="count">{count}</span>
            </li>
          {/each}
          {#if stats.unmapped_count > 0}
            <li class="missing">
              <span class="label">no value</span>
              <span class="bar" style:width="{(stats.unmapped_count / most) * 100}%"></span>
              <span class="count">{stats.unmapped_count}</span>
            </li>
          {/if}
        </ul>
      {:else if previewLoading}
        <p class="hint">Updating preview…</p>
      {/if}
    {:else}
      <p class="subtitle">Estimate <span class="globi">(GloBI: prior)</span> <Explain text={help.estimate} tip /></p>
      <Explain text={help.estimate} />
      {#if field.name}
        {#key field.name}
          <EstimateEditor target={field.name} asCounts showPreview />
        {/key}
      {:else}
        <p class="hint">Name it first.</p>
      {/if}
    {/if}
  </section>

  <section>
    <h3>What does it change in the model? <Explain text={help.parts} tip /></h3>
    <Explain text={help.parts} />
    <p class="subtitle">Parts <span class="globi">(GloBI: component map)</span></p>
    {#if field.name && $partRulesStore.rules}
      {@const using = partsUsing($partRulesStore.rules, field.name)}
      <p class="hint">
        {using.length ? `Decides ${using.map(partLabel).join(', ')}.` : 'No model part depends on it yet.'}
        <button type="button" class="btn btn-link" onclick={() => navigateTo('model-parts')}>Change on Component Map</button>
      </p>
    {:else if field.name}
      <ModelPartsChecklist fieldName={field.name} {fieldOrder} {onShowConnections} />
      {#if view.recordCount > 0}
        <p class="hint totals">
          Together these need {view.recordCount.toLocaleString()} library record{view.recordCount === 1 ? '' : 's'}.
        </p>
      {/if}
    {:else}
      <p class="hint">Name it first.</p>
    {/if}
  </section>
</article>

<style>
  .card {
    gap: var(--space-5);
  }

  .card-header {
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }

  .name {
    flex: 1;
  }

  .name input {
    width: 100%;
    font-size: var(--text-lg);
    font-weight: 600;
  }

  section {
    border-top: 1px solid var(--border);
    padding-top: var(--space-4);
  }

  h3 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-md);
  }

  section :global(.explain) {
    margin-bottom: var(--space-3);
  }

  p {
    margin: 0 0 var(--space-2);
    font-size: var(--text-sm);
  }

  .subtitle {
    font-weight: 600;
  }

  .globi {
    font-weight: 300;
    color: var(--text-muted);
  }

  .issues {
    padding-left: var(--space-6);
  }

  .choice {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }

  .choice button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }

  .choice button strong {
    font-weight: 600;
  }

  .choice button span {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .choice button.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .totals {
    margin-top: var(--space-3);
  }

  .spread {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: minmax(80px, max-content) minmax(0, 1fr) auto;
    gap: 4px var(--space-2);
    align-items: center;
    font-size: var(--text-sm);
  }

  .spread.stale {
    opacity: 0.7;
  }

  .spread li {
    display: contents;
  }

  .spread .bar {
    height: 12px;
    min-width: 2px;
    border-radius: 2px;
    background: var(--accent);
  }

  .spread .count {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .spread .missing .label,
  .spread .missing .count {
    color: var(--err-text);
  }

  .spread .missing .bar {
    background: var(--err-text);
  }
</style>
