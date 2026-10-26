<script lang="ts">
  /**
   * Adding a characteristic, as the two questions a new region starts from: what does
   * your data already tell you (one chip per unused GIS column), and what do you need to
   * estimate (common residential characteristics, with their usual values). Either way
   * the new characteristic opens in its card to finish.
   */
  import { onMount } from 'svelte';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { createEmptyField, ensureTransformationRule } from '../../utils/semanticFieldRules';
  import type { GISColumn, SemanticField } from '../../types/semanticFields';

  /** Where the estimate suggestions come from: the full residential example's sampled fields. */
  const SUGGESTIONS_TEMPLATE = 'residential.yml';
  /** A text column with at most this many values starts with one value per GIS value. */
  const MAX_DIRECT_VALUES = 8;

  let { onAdded, onCancel }: { onAdded: (id: string) => void; onCancel?: () => void } = $props();

  let suggestions = $state<Array<{ name: string; options: string[]; description?: string }>>([]);

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

  onMount(async () => {
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

  function describe(column: GISColumn): string {
    if (column.dataType === 'numeric') return 'numbers';
    return `${column.uniqueValues.length} value${column.uniqueValues.length === 1 ? '' : 's'}`;
  }
</script>

<div class="add">
  <section>
    <h3>1. What does your data already tell you?</h3>
    <p class="muted">
      Pick a column that sets buildings apart, such as year built or building use. You will group its values into a
      few classes next.
    </p>
    {#if columns.length > 0}
      <div class="chips">
        {#each columns as column (column.name)}
          <button type="button" class="chip" onclick={() => fromColumn(column)}>
            {column.name} <span class="muted">· {describe(column)}</span>
          </button>
        {/each}
      </div>
    {:else if editor.gisColumns.length === 0}
      <p class="muted">No GIS data yet. Validate it in GIS Cleaning to pick from its columns.</p>
    {:else}
      <p class="muted">Every column is already used.</p>
    {/if}
  </section>

  <section>
    <h3>2. What do you need to estimate?</h3>
    <p class="muted">
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

  <div class="row">
    <button type="button" class="btn btn-secondary btn-sm" onclick={() => add(createEmptyField())}>Something else</button>
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
  }

  p {
    margin: 0 0 var(--space-3);
    font-size: var(--text-sm);
  }

  .muted {
    color: var(--text-muted);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .chip {
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--accent-soft);
    color: var(--text);
    padding: 4px 10px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
  }

  .chip.estimate {
    background: color-mix(in srgb, var(--series-5) 18%, var(--surface));
  }

  .chip:hover {
    border-color: var(--accent);
  }

  .row {
    display: flex;
    gap: 8px;
  }
</style>
