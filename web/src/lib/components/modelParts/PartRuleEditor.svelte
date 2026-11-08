<script lang="ts">
  /**
   * One part, in the side panel: the same option for every building, or an option per value
   * of the characteristics it varies by. Options show the value that sets them apart (W/m²,
   * U-value, COP); one colour is one library record, so rows that share a colour share it.
   * Pickers and forms open only when a pill or button is clicked.
   */
  import Icon from '../Icon.svelte';
  import Explain from '../Explain.svelte';
  import SchemaForm from '../componentLibrary/SchemaForm.svelte';
  import ComponentPriorEditor from '../priors/ComponentPriorEditor.svelte';
  import { componentPriorsStore } from '../../stores/componentPriorsStore';
  import { priorFor } from '../../utils/componentPriors';
  import { constructionForU, type ComponentRecord } from '../../api/componentLibrary';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { createEmptyField, parseOptionsText } from '../../utils/semanticFieldRules';
  import { constructionType, keyValue } from '../../utils/optionValues';
  import {
    GENERATED_PREFIX,
    emptyRule,
    rowCount,
    rowsOf,
    setDefault,
    setOption,
    usedOptions,
    withDependency,
    withoutDependency,
    type PartRule,
  } from '../../utils/partRules';
  import { HELP } from '../../help';
  const help = HELP.componentMap;

  const MAX_ROWS = 200;
  const DEFAULT_KEY = '';

  let {
    type,
    path,
    label,
    rule,
    records,
    conductivity,
    onChange,
    onRecordsChanged,
    onNext,
  }: {
    /** The library type this part's options are records of. */
    type: string;
    path: string;
    label: string;
    rule: PartRule | undefined;
    /** This type's library records (options), with their fields; null while they load. */
    records: ComponentRecord[] | null;
    /** Material conductivities, for construction U-values. */
    conductivity: Record<string, number>;
    onChange: (rule: PartRule) => void;
    onRecordsChanged: () => Promise<void>;
    onNext: (() => void) | null;
  } = $props();

  const current = $derived(rule ?? emptyRule());
  const fields = $derived($semanticFieldsStore.fields.filter((field) => field.name));
  const fieldOrder = $derived(fields.map((field) => field.name));
  const options = $derived(Object.fromEntries(fields.map((field) => [field.name, field.options])));
  const rows = $derived(rowsOf(current, options, MAX_ROWS));
  const total = $derived(rowCount(current, options));
  const byName = $derived(Object.fromEntries((records ?? []).map((record) => [record.Name, record])));
  /** One colour per option in use, in the order the rows use them. */
  const used = $derived(usedOptions(current, options, MAX_ROWS));
  const isConstruction = $derived(type === 'ConstructionAssembly');
  const candidates = $derived.by(() => {
    const own = (records ?? []).filter((record) => !record.Name.startsWith(GENERATED_PREFIX));
    // constructions of this part's kind first: a wall's options are walls
    const kind = isConstruction ? own.filter((record) => record.Type === constructionType(path)) : own;
    return (kind.length ? kind : own).filter((record) => record.Name.toLowerCase().includes(filter.toLowerCase()));
  });

  let mode = $state<'same' | 'varies' | null>(null);
  const shown = $derived(mode ?? (current.depends_on.length > 0 ? 'varies' : 'same'));
  /** "Same for every building" is only highlighted once someone chose it; untouched parts are defaults. */
  const sameChosen = $derived(shown === 'same' && (current.confirmed || mode === 'same'));
  /** The row whose option is being picked (DEFAULT_KEY: the one for every building). */
  let picking = $state<string | null>(null);
  let filter = $state('');
  let creating = $state<'u' | 'form' | null>(null);
  let target = $state(0.3);
  let created = $state<string | null>(null);
  let error = $state<string | null>(null);
  let addingField = $state(false);
  /** The row whose component's uncertainty is open. */
  let uncertain = $state<string | null>(null);
  let newField = $state({ name: '', values: '' });

  const colour = (name: string | null) =>
    name && used.includes(name) ? `var(--series-${(used.indexOf(name) % 8) + 1})` : 'var(--border-strong)';
  const valueOf = (name: string | null) => (name ? keyValue(type, byName[name], conductivity) || name : 'Choose…');

  function same() {
    if (current.depends_on.length > 0 && !confirm(`${label} will use one option for every building. Continue?`)) return;
    mode = 'same';
    onChange({ ...current, depends_on: [], cells: {}, confirmed: true });
  }

  function toggle(name: string) {
    if (current.depends_on.includes(name)) {
      const { rule: merged, conflicts } = withoutDependency(current, name, options);
      if (conflicts && !confirm(`${conflicts} merged row(s) had different options; each keeps the most common one. Continue?`)) return;
      onChange(merged);
    } else {
      onChange(withDependency(current, name, fieldOrder, options));
    }
  }

  function addCharacteristic() {
    const name = newField.name.trim();
    const values = parseOptionsText(newField.values);
    if (!name || values.length === 0 || fieldOrder.includes(name)) return;
    // typed now, bound to a GIS column or estimated later (Building Characteristics lists it to finish)
    semanticFieldsStore.addField({ ...createEmptyField(), name, options: values });
    onChange(withDependency(current, name, [...fieldOrder, name], { ...options, [name]: values }));
    newField = { name: '', values: '' };
    addingField = false;
  }

  function openPicker(key: string) {
    picking = picking === key ? null : key;
    uncertain = null;
    filter = '';
    creating = null;
    error = null;
  }

  function assign(option: string) {
    const key = picking ?? DEFAULT_KEY;
    // picking the one component for every building decides the part: it is no longer a default
    onChange(key === DEFAULT_KEY ? { ...setDefault(current, option), confirmed: current.depends_on.length === 0 } : setOption(current, key, option));
    picking = null;
    creating = null;
  }

  async function createFromU() {
    error = null;
    try {
      const name = `${label} U ${target}`;
      const result = await constructionForU(name, constructionType(path), target);
      await onRecordsChanged();
      created = `Reached U ${result.u_value.toFixed(2)} W/m²K`;
      assign(name);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not make the construction.';
    }
  }

  async function savedForm(record: Record<string, unknown>) {
    await onRecordsChanged();
    assign(String(record.Name));
  }

  function openPrior(key: string) {
    uncertain = uncertain === key ? null : key;
    picking = null;
  }

  /** How many other rows share a row's component, and so its uncertainty. */
  function shared(key: string, option: string): string {
    const others = rows.filter((row) => row.key !== key && row.option === option).length;
    return key !== DEFAULT_KEY && others > 0 ? `${others} other row${others === 1 ? '' : 's'} use${others === 1 ? 's' : ''} this component too.` : '';
  }

  const optionFor = (key: string) => (key === DEFAULT_KEY ? current.default : (rows.find((row) => row.key === key)?.option ?? null));
</script>

{#snippet pill(key: string, option: string | null)}
  <button type="button" class="pill" class:open={picking === key} aria-expanded={picking === key} title={option ?? ''} onclick={() => openPicker(key)}>
    <span class="dot" style:background={colour(option)}></span>
    <span class="value">{valueOf(option)}</span>
    <Icon name="chevron-down" size={14} />
  </button>
{/snippet}

{#snippet uncertainty(key: string, option: string | null)}
  {#if option}
    {@const on = priorFor($componentPriorsStore, type, option) !== null}
    <button type="button" class="unc" class:on class:open={uncertain === key} aria-expanded={uncertain === key}
      aria-label={on ? 'Edit its uncertainty' : 'Make it uncertain'} title={on ? 'Uncertain: edit its curve' : 'Make a value of this component uncertain'} onclick={() => openPrior(key)}>
      <Icon name="bell-curve" size={14} />
    </button>
  {/if}
{/snippet}

{#snippet priorPanel(key: string, option: string | null)}
  {#if uncertain === key && option}
    <div class="prior-panel">
      <ComponentPriorEditor {type} name={option} record={byName[option] ?? null} {conductivity} note={shared(key, option)} />
    </div>
  {/if}
{/snippet}

{#snippet picker()}
  <div class="picker">
    {#if creating === 'form'}
      <SchemaForm componentType={type} mode="create" copyFrom={optionFor(picking ?? DEFAULT_KEY)} onSaved={savedForm} onCancel={() => (creating = null)} />
    {:else}
      {#if records === null}
        <p class="hint">Loading options…</p>
      {:else if records.length > 12}
        <input class="filter" placeholder="Filter" bind:value={filter} aria-label="Filter options" />
      {/if}
      <ul class="choices">
        {#each candidates as record (record.Name)}
          <li>
            <button type="button" class="choice" class:chosen={record.Name === optionFor(picking ?? DEFAULT_KEY)} title={record.Name} onclick={() => assign(record.Name)}>
              <span class="dot" style:background={colour(record.Name)}></span>
              <span class="value">{keyValue(type, record, conductivity) || record.Name}</span>
              <span class="name">{record.Name}</span>
            </button>
          </li>
        {/each}
      </ul>
      {#if creating === 'u'}
        <form class="inline" onsubmit={(event) => { event.preventDefault(); void createFromU(); }}>
          <label>U-value <input type="number" step="0.01" min="0.05" bind:value={target} aria-label="Target U-value" /> W/m²K</label>
          <button type="submit" class="btn btn-sm">Make it</button>
        </form>
      {:else}
        <div class="new">
          {#if isConstruction}
            <button type="button" class="btn btn-secondary btn-sm" onclick={() => (creating = 'u')}><Icon name="plus" size={14} />By U-value</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick={() => (creating = 'form')}><Icon name="plus" size={14} />Build layers</button>
          {:else}
            <button type="button" class="btn btn-secondary btn-sm" onclick={() => (creating = 'form')}><Icon name="plus" size={14} />New option</button>
          {/if}
        </div>
        {#if isConstruction}<Explain text={help.construction} />{/if}
      {/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
    {/if}
  </div>
{/snippet}

<div class="editor">
  <Explain text={help.editor} />
  <div class="toggle" data-tour="part-mode" role="radiogroup" aria-label={`How ${label} is chosen`}>
    <button type="button" role="radio" aria-checked={sameChosen} class:selected={sameChosen} onclick={same}>Same for every building</button>
    <button type="button" role="radio" aria-checked={shown === 'varies'} class:selected={shown === 'varies'} onclick={() => (mode = 'varies')}>Varies by…</button>
  </div>

  {#if shown === 'same'}
    <div class="row single">
      {@render pill(DEFAULT_KEY, current.default)}
      {@render uncertainty(DEFAULT_KEY, current.default)}
      {#if !sameChosen}<span class="tag" title="Nobody has decided this part yet; it uses the archetype's component">default</span>{/if}
    </div>
    {#if picking === DEFAULT_KEY}{@render picker()}{/if}
    {@render priorPanel(DEFAULT_KEY, current.default)}
  {:else}
    <div class="chips" data-tour="part-mode" role="group" aria-label="Characteristics it varies by">
      {#each fields as field (field.id)}
        <button type="button" class="chip" class:on={current.depends_on.includes(field.name)} aria-pressed={current.depends_on.includes(field.name)} onclick={() => toggle(field.name)}>
          {field.name}
        </button>
      {/each}
      <button type="button" class="chip add" aria-expanded={addingField} title="A characteristic your data doesn't have yet" onclick={() => (addingField = !addingField)}>
        <Icon name="plus" size={12} />New
      </button>
    </div>
    {#if addingField}
      <form class="inline" onsubmit={(event) => { event.preventDefault(); addCharacteristic(); }}>
        <input placeholder="Name, e.g. LightingTech" bind:value={newField.name} aria-label="New characteristic name" />
        <input placeholder="Values, e.g. NoLED, LED" bind:value={newField.values} aria-label="New characteristic values" />
        <button type="submit" class="btn btn-sm">Add</button>
      </form>
    {/if}

    {#if current.depends_on.length > 0}
      <ul class="rows" data-tour="part-rows">
        {#each rows as row (row.key)}
          <li>
            <div class="row">
              <span class="values">{current.depends_on.map((name) => row.values[name]).join(' · ')}</span>
              <span class="choose">{@render pill(row.key, row.option)}{@render uncertainty(row.key, row.option)}</span>
            </div>
            {#if picking === row.key}{@render picker()}{/if}
            {@render priorPanel(row.key, row.option)}
          </li>
        {/each}
      </ul>
      {#if total > rows.length}<p class="hint">{(total - rows.length).toLocaleString()} more rows use {valueOf(current.default)}.</p>{/if}
    {/if}
  {/if}

  {#if created}<p class="hint ok"><Icon name="check" size={14} /> {created}</p>{/if}
  {#if onNext}
    <div class="next"><button type="button" class="btn btn-sm btn-secondary" onclick={onNext}>Next part <Icon name="arrow-right" size={14} /></button></div>
  {/if}
</div>

<style>
  .editor { display: flex; flex-direction: column; gap: var(--space-3); }
  .toggle { display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); overflow: hidden; align-self: flex-start; }
  .toggle button { min-height: var(--control-h-sm); padding: 0 var(--space-3); border: none; background: var(--surface); color: var(--text-2); font-size: var(--text-sm); cursor: pointer; }
  .toggle button + button { border-left: 1px solid var(--border-strong); }
  .toggle button.selected { background: var(--accent-soft); color: var(--text); font-weight: 600; }
  .chips { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .chip { min-height: 24px; border: 1px solid var(--border-strong); background: var(--surface); color: var(--text-2); border-radius: var(--radius-sm); padding: 0 var(--space-2); font-size: var(--text-xs); font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 2px; }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  .chip.add { border-style: dashed; }
  .inline { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; font-size: var(--text-sm); }
  .inline input { min-width: 140px; }
  .inline input[type='number'] { width: 80px; min-width: 0; }
  .rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .rows li { border-bottom: 1px solid var(--border); }
  .row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-1) 0; font-size: var(--text-sm); }
  .row.single { justify-content: flex-start; }
  .values { color: var(--text); }
  .pill { display: inline-flex; align-items: center; gap: var(--space-2); min-height: var(--control-h-sm); padding: 0 var(--space-2); border: 1px solid var(--border); border-radius: 999px; background: var(--surface); color: var(--text); font-size: var(--text-sm); cursor: pointer; }
  .pill.open, .pill:hover { border-color: var(--accent); }
  .choose { display: inline-flex; align-items: center; gap: var(--space-1); }
  .unc { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border: 1px dashed var(--border-strong); border-radius: 999px; background: var(--surface); color: var(--text-muted); cursor: pointer; }
  .unc:hover, .unc.open { border-color: var(--accent); color: var(--accent); }
  .unc.on { border-style: solid; border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
  .prior-panel { padding: var(--space-2) 0 var(--space-3); }
  .dot { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }
  .picker { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-2) 0 var(--space-3); }
  .filter { max-width: 240px; }
  .choices { list-style: none; margin: 0; padding: 0; max-height: 280px; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .choice { width: 100%; display: grid; grid-template-columns: 12px auto minmax(0, 1fr); align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2); border: none; background: none; text-align: left; cursor: pointer; font-size: var(--text-sm); color: var(--text); }
  .choice:hover, .choice.chosen { background: var(--accent-soft); }
  .choice .name { color: var(--text-muted); font-size: var(--text-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .new { display: flex; gap: var(--space-2); }
  .next { display: flex; justify-content: flex-end; }
  .ok { color: var(--ok-text); display: inline-flex; align-items: center; gap: 4px; }
  .tag { font-size: var(--text-xs); color: var(--warn-text); background: var(--warn-bg); border-radius: var(--radius-sm); padding: 0 6px; }
</style>
