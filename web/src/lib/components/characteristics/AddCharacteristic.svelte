<script lang="ts">
  /**
   * Adding a characteristic, as the two questions a new region starts from: what does
   * your data already tell you (one chip per unused GIS column), and what do you need to
   * estimate (common residential characteristics, with their usual values). A project made
   * from a stock-model template also offers that model's characteristics, whose options are
   * library records already, so adding one also sets the rule of the part it decides. Either
   * way the new characteristic opens in its card to finish.
   */
  import { onMount } from 'svelte';
  import { fetchStockPreset, type StockPreset } from '../../api/partRules';
  import { partRulesStore } from '../../stores/partRulesStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { createEmptyField, ensureTransformationRule } from '../../utils/semanticFieldRules';
  import type { GISColumn, SemanticField } from '../../types/semanticFields';

  /** Where the estimate suggestions come from: the full residential example's sampled fields. */
  const SUGGESTIONS_TEMPLATE = 'residential.yml';
  /** A text column with at most this many values starts with one value per GIS value. */
  const MAX_DIRECT_VALUES = 8;

  let { onAdded, onCancel }: { onAdded: (id: string) => void; onCancel?: () => void } = $props();

  let suggestions = $state<Array<{ name: string; options: string[]; description?: string }>>([]);
  let preset = $state<StockPreset | null>(null);
  let picking = $state<StockPreset['characteristics'][number] | null>(null);
  let ticked = $state<string[]>([]);

  const editor = $derived($semanticFieldsStore);
  const taken = $derived(new Set(editor.fields.map((field) => field.name)));
  const columns = $derived(
    editor.gisColumns.filter(
      (column) =>
        column.name !== editor.buildingIdCol &&
        column.name !== editor.numFloorsCol &&
        !editor.fields.some((field) => field.transformationRule?.sourceColumn === column.name)
    )
  );
  const openSuggestions = $derived(suggestions.filter((entry) => !taken.has(entry.name)));
  const openPreset = $derived((preset?.characteristics ?? []).filter((entry) => !taken.has(entry.name)));

  onMount(async () => {
    fetchStockPreset()
      .then((loaded) => (preset = loaded))
      .catch(() => {});
    try {
      const response = await fetch(`/api/semantic-fields/templates/${SUGGESTIONS_TEMPLATE}`);
      const template = await response.json();
      suggestions = ((template.Fields as Record<string, unknown>[]) ?? [])
        .filter((entry) => entry.Type === 'stochastic')
        .map((entry) => ({
          name: String(entry.Name),
          options: (entry.Options as string[]) ?? [],
          description: entry.Description ? String(entry.Description) : undefined,
        }));
    } catch {
      // Suggestions are a shortcut; "Something else" still works without them.
    }
  });

  function add(field: SemanticField) {
    semanticFieldsStore.addField(field);
    semanticFieldsStore.setSelectedField(field.id);
    onAdded(field.id);
  }

  function fromColumn(column: GISColumn) {
    const numeric = column.dataType === 'numeric';
    const direct = !numeric && column.uniqueValues.length > 0 && column.uniqueValues.length <= MAX_DIRECT_VALUES;
    const field: SemanticField = {
      ...createEmptyField(),
      name: column.name,
      dataType: numeric ? 'numeric' : 'categorical',
      options: direct ? [...column.uniqueValues] : [],
      transformationRule: {
        id: crypto.randomUUID(),
        type: numeric ? 'numeric_range' : 'categorical_mapping',
        sourceColumn: column.name,
        targetField: column.name,
      },
    };
    add(ensureTransformationRule(field, editor.gisColumns));
  }

  function toEstimate(entry: { name: string; options: string[]; description?: string }) {
    add({
      ...createEmptyField(),
      name: entry.name,
      type: 'stochastic',
      requiresPrior: true,
      options: [...entry.options],
      description: entry.description,
    });
  }

  /** The ticked options become the characteristic's values, each picking its record for every part. */
  function fromPreset() {
    if (!picking || !preset) return;
    const { name, parts, options } = picking;
    const [first, ...rest] = Object.keys(options).filter((option) => ticked.includes(option));
    if (first === undefined) return;
    for (const part of parts) {
      partRulesStore.setPart(part, {
        depends_on: [name],
        default: options[first],
        cells: Object.fromEntries(rest.map((option) => [option, options[option]])),
        confirmed: true,
      });
    }
    add({
      ...createEmptyField(),
      name,
      options: [first, ...rest],
      description: `ResStock ${preset.source.tag}: ${name}`,
    });
    picking = null;
  }

  function describe(column: GISColumn): string {
    if (column.dataType === 'numeric') return 'numbers';
    return `${column.uniqueValues.length} value${column.uniqueValues.length === 1 ? '' : 's'}`;
  }
</script>

<div class="add">
  <section data-tour="char-from-data">
    <h3>What does your data already tell you?</h3>
    <p class="hint">
      Pick a column that sets buildings apart, such as year built or building use. You will group its values into a
      few classes next.
    </p>
    {#if columns.length > 0}
      <div class="chips">
        {#each columns as column (column.name)}
          <button type="button" class="chip" onclick={() => fromColumn(column)}>
            {column.name} <span class="chip-meta">· {describe(column)}</span>
          </button>
        {/each}
      </div>
    {:else if editor.gisColumns.length === 0}
      <p class="hint">No GIS data yet. Validate it in GIS Cleaning to pick from its columns.</p>
    {:else}
      <p class="hint">Every column is already used.</p>
    {/if}
  </section>

  <section data-tour="char-estimate">
    <h3>What do you need to estimate?</h3>
    <p class="hint">
      Things your data doesn't record, such as heating system or wall insulation. Each building gets a value drawn
      from odds you set, so results carry that uncertainty.
    </p>
    {#if openSuggestions.length > 0}
      <div class="chips">
        {#each openSuggestions as entry (entry.name)}
          <button type="button" class="chip estimate" title={entry.description} onclick={() => toEstimate(entry)}>
            {entry.name}
          </button>
        {/each}
      </div>
    {/if}
  </section>

  {#if preset && openPreset.length > 0}
    <section>
      <h3>From ResStock {preset.source.tag}</h3>
      <p class="hint">
        ResStock's characteristics, each option already a library record for the part it decides. Keep only the
        options your buildings have.
      </p>
      {#if picking}
        <fieldset class="options">
          <legend>{picking.name}</legend>
          {#each Object.keys(picking.options) as option (option)}
            <label><input type="checkbox" value={option} bind:group={ticked} /> {option}</label>
          {/each}
        </fieldset>
        <div class="actions">
          <button type="button" class="btn btn-sm" disabled={ticked.length === 0} onclick={fromPreset}>
            Add with {ticked.length} option{ticked.length === 1 ? '' : 's'}
          </button>
          <button type="button" class="btn btn-ghost btn-sm" onclick={() => (picking = null)}>Back</button>
        </div>
      {:else}
        <div class="chips">
          {#each openPreset as entry (entry.name)}
            <button
              type="button"
              class="chip"
              title="Decides {entry.parts.join(', ')}"
              onclick={() => {
                picking = entry;
                ticked = [];
              }}
            >
              {entry.name} <span class="chip-meta">· {Object.keys(entry.options).length} options</span>
            </button>
          {/each}
        </div>
      {/if}
      <details class="assumptions">
        <summary>How ResStock's values were converted</summary>
        <ul>
          {#each preset.assumptions as assumption (assumption)}
            <li>{assumption}</li>
          {/each}
        </ul>
      </details>
    </section>
  {/if}

  <div class="actions">
    <button
      type="button"
      class="btn btn-secondary btn-sm"
      title="Type its values now; bind it to a GIS column or make it an estimate later"
      onclick={() => add(createEmptyField())}
    >
      Something I know varies
    </button>
    {#if onCancel}
      <button type="button" class="btn btn-ghost btn-sm" onclick={onCancel}>Cancel</button>
    {/if}
  </div>
</div>

<style>
  .add {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  h3 {
    margin: 0 0 var(--space-1);
    font-size: var(--text-md);
    font-weight: 600;
  }

  p {
    margin: 0 0 var(--space-3);
    font-size: var(--text-sm);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  /* Pick-to-add chips, tinted like the from-data / estimated tags in the list. */
  .chip {
    min-height: var(--control-h-sm);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--accent-soft);
    color: var(--text);
    padding: 0 var(--space-3);
    font-size: var(--text-sm);
    font-weight: 500;
    cursor: pointer;
  }

  .chip.estimate {
    background: color-mix(in srgb, var(--series-5) 18%, var(--surface));
  }

  .chip:hover {
    border-color: var(--accent);
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    max-height: 16rem;
    overflow-y: auto;
    margin: 0 0 var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
  }

  .assumptions {
    margin-top: var(--space-3);
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .chip-meta {
    color: var(--text-muted);
    font-weight: 300;
  }
</style>
