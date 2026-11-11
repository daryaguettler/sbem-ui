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
  import { priorTreesStore } from '../../stores/priorTreesStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { createEmptyField, ensureTransformationRule } from '../../utils/semanticFieldRules';
  import type { GISColumn, SemanticField } from '../../types/semanticFields';
  import Select from '../Select.svelte';

  /** Where the estimate suggestions come from: the full residential example's sampled fields. */
  const SUGGESTIONS_TEMPLATE = 'residential.yml';
  /** A text column with at most this many values starts with one value per GIS value. */
  const MAX_DIRECT_VALUES = 8;

  let { onAdded, onCancel }: { onAdded: (id: string) => void; onCancel?: () => void } = $props();

  let suggestions = $state<Array<{ name: string; options: string[]; description?: string }>>([]);
  let preset = $state<StockPreset | null>(null);
  let picking = $state<StockPreset['characteristics'][number] | null>(null);
  let ticked = $state<string[]>([]);
  /** Narrow ResStock's options to one state: per characteristic, its homes' share of each option (null: no location data). */
  let states = $state<string[]>([]);
  let usState = $state('');
  let stateShares = $state<Record<string, Record<string, number> | null>>({});
  /** With a state picked, options at least this common there start ticked. */
  const COMMON_SHARE = 0.01;
  const pickingShares = $derived(picking && usState ? stateShares[picking.name] : null);
  const shownOptions = $derived(
    picking ? Object.keys(picking.options).filter((option) => !pickingShares || option in pickingShares) : []
  );

  async function pickState(value: string) {
    usState = value;
    stateShares = {};
    if (!value) return;
    const response = await fetch(`/api/prior-trees/resstock-state-options?state=${encodeURIComponent(value)}`);
    if (response.ok) stateShares = (await response.json()).options;
    if (picking) startPicking(picking);
  }

  function startPicking(entry: StockPreset['characteristics'][number]) {
    picking = entry;
    const shares = usState ? stateShares[entry.name] : null;
    ticked = shares ? Object.keys(entry.options).filter((option) => (shares[option] ?? 0) >= COMMON_SHARE) : [];
  }

  const percent = (share: number) => (share < 0.001 ? '<0.1%' : `${(share * 100).toFixed(1)}%`);

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
  /** "Based on another characteristic": a parent with values, each mapped to one value of the new one. */
  const parents = $derived(editor.fields.filter((field) => (field.options?.length ?? 0) > 0));
  let deriving = $state<SemanticField | null>(null);
  let derivedName = $state('');
  let derivedMap = $state<Record<string, string>>({});
  const derivedValues = $derived([...new Set(Object.values(derivedMap).map((value) => value.trim()))]);
  const derivedReady = $derived(
    Boolean(derivedName.trim()) && !taken.has(derivedName.trim()) && !derivedValues.includes('')
  );

  function startDeriving(parent: SemanticField) {
    deriving = parent;
    derivedName = `${parent.name} group`;
    derivedMap = Object.fromEntries(parent.options.map((option) => [option, option]));
  }

  /** Saved as an estimate conditioned on the parent whose table gives each parent value one child value. */
  function fromParent() {
    if (!deriving || !derivedReady) return;
    const name = derivedName.trim();
    priorTreesStore.setJoint({
      target: name,
      condition_on: [deriving.name],
      table: Object.fromEntries(
        Object.entries(derivedMap).map(([parent, child]) => [
          parent,
          Object.fromEntries(derivedValues.map((value) => [value, value === child.trim() ? 1 : 0])),
        ])
      ),
    });
    add({
      ...createEmptyField(),
      name,
      type: 'stochastic',
      requiresPrior: true,
      options: derivedValues,
      description: `Mapped from ${deriving.name}`,
    });
    deriving = null;
  }

  const openSuggestions = $derived(suggestions.filter((entry) => !taken.has(entry.name)));
  const openPreset = $derived((preset?.characteristics ?? []).filter((entry) => !taken.has(entry.name)));

  onMount(async () => {
    fetchStockPreset()
      .then((loaded) => {
        preset = loaded;
        if (loaded) {
          fetch('/api/prior-trees/resstock-states')
            .then((response) => response.json())
            .then((data) => (states = data.states ?? []))
            .catch(() => {});
        }
      })
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

  <section>
    <h3>Based on another characteristic</h3>
    <p class="hint">
      Group or rename the values of one you already have, e.g. typology → residential / commercial. Each building gets
      the value its own value maps to. Give two values the same name to merge them.
    </p>
    {#if deriving}
      <label class="field">
        Name
        <input type="text" bind:value={derivedName} />
        {#if taken.has(derivedName.trim())}<span class="field-hint">A characteristic with this name exists.</span>{/if}
      </label>
      <table class="map">
        <thead><tr><th>{deriving.name}</th><th>{derivedName || 'New value'}</th></tr></thead>
        <tbody>
          {#each Object.keys(derivedMap) as parentValue (parentValue)}
            <tr>
              <td>{parentValue}</td>
              <td><input type="text" aria-label={`Value for ${parentValue}`} bind:value={derivedMap[parentValue]} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="actions">
        <button type="button" class="btn btn-sm" disabled={!derivedReady} onclick={fromParent}>
          Add with {derivedValues.length} value{derivedValues.length === 1 ? '' : 's'}
        </button>
        <button type="button" class="btn btn-ghost btn-sm" onclick={() => (deriving = null)}>Back</button>
      </div>
    {:else if parents.length > 0}
      <div class="chips">
        {#each parents as parent (parent.id)}
          <button type="button" class="chip" onclick={() => startDeriving(parent)}>
            {parent.name} <span class="chip-meta">· {parent.options.length} values</span>
          </button>
        {/each}
      </div>
    {:else}
      <p class="hint">Add a characteristic with values first.</p>
    {/if}
  </section>

  {#if preset && openPreset.length > 0}
    <section>
      <h3>From ResStock {preset.source.tag}</h3>
      <p class="hint">
        ResStock's characteristics, each option already a library record for the part it decides. Keep only the
        options your buildings have.
      </p>
      {#if states.length > 0}
        <div class="state-pick">
          <span>Only options found in</span>
          <Select
            value={usState}
            ariaLabel="US state"
            options={[{ value: '', label: 'All states' }, ...states.map((code) => ({ value: code, label: code }))]}
            onChange={pickState}
          />
        </div>
      {/if}
      {#if picking}
        {#if usState && pickingShares === null && picking.name in stateShares}
          <p class="hint">ResStock's {picking.name} odds don't depend on location, so every option is shown.</p>
        {:else if pickingShares}
          <p class="hint">
            Showing the {shownOptions.length} of {Object.keys(picking.options).length} options found in {usState}, with
            their share of its homes. Those at {COMMON_SHARE * 100}% or more start ticked.
          </p>
        {/if}
        <fieldset class="options">
          <legend>{picking.name}</legend>
          {#each shownOptions as option (option)}
            <label>
              <input type="checkbox" value={option} bind:group={ticked} />
              {option}
              {#if pickingShares}<span class="chip-meta">· {percent(pickingShares[option])}</span>{/if}
            </label>
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
              onclick={() => startPicking(entry)}
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

  .map {
    margin: var(--space-3) 0;
    font-size: var(--text-sm);
  }

  .map td,
  .map th {
    padding: var(--space-1) var(--space-2);
    text-align: left;
  }

  .state-pick {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-3);
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
