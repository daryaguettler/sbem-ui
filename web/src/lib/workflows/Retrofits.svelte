<script lang="ts">
  /**
   * Retrofit packages (retrofits.yaml): each package is a list of measures that set a
   * semantic field to a better option, optionally only where another field has a given
   * value. "Never downgrade" orders a field's options so a measure only ever moves a
   * building up. A measure can also act on a model part: replace its component, or shift one
   * of its numbers (scale, add, at most, at least), uncertain components variant by variant.
   */
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import { fetchSavedArtifact, formatSavedAt, saveArtifact } from '../api/artifacts';
  import { markSaved, savedAt } from '../stores/projectArtifacts';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import Explain from '../components/Explain.svelte';
  import Select from '../components/Select.svelte';
  import Icon from '../components/Icon.svelte';
  import { fetchParts, type PartInfo } from '../api/partRules';
  import { fetchComponentRecords, fetchComponentSchema } from '../api/componentLibrary';
  import { partLabel } from '../utils/modelParts';
  import { U, keyField } from '../utils/componentPriors';
  import { HELP } from '../help';
  const help = HELP.retrofits;

  interface Condition {
    field: string;
    in?: string[];
    not_in?: string[];
  }
  type Shift = 'scale' | 'add' | 'at_most' | 'at_least';
  interface Measure {
    field?: string;
    part?: string;
    number?: string;
    op?: Shift;
    value?: number;
    to?: string;
    map?: Record<string, string>;
    when?: Condition[] | Condition;
  }
  interface Package {
    name: string;
    measures: Measure[];
  }
  interface RetrofitsDoc {
    upgrade_order: Record<string, string[]>;
    packages: Package[];
  }

  let doc: RetrofitsDoc = { upgrade_order: {}, packages: [] };
  let loading = true;
  let saving = false;
  let dirty = false;
  let error: string | null = null;

  /** The package whose "+ measure" row is open, and that row's draft. */
  let adding: number | null = null;
  let draft = { kind: 'field', field: '', to: '', part: '', op: 'to', number: '', value: '', ifField: '', ifValue: '' };

  const ACTIONS = [
    { value: 'to', label: 'replace with' },
    { value: 'scale', label: 'multiply' },
    { value: 'add', label: 'add' },
    { value: 'at_most', label: 'at most' },
    { value: 'at_least', label: 'at least' },
  ];
  const SHOWN: Record<Shift, string> = { scale: '×', add: '+', at_most: 'at most', at_least: 'at least' };
  let parts: PartInfo[] = [];
  /** The draft part's records (replace with) and numbers (shift). */
  let partRecords: string[] = [];
  let partNumbers: string[] = [];

  $: options = Object.fromEntries(
    $semanticFieldsStore.fields
      .filter((f) => f.options && f.options.length > 0)
      .map((f) => [f.name, f.options])
  ) as Record<string, string[]>;
  $: fieldNames = Object.keys(options);
  $: usedFields = [...new Set(doc.packages.flatMap((p) => p.measures.flatMap((m) => (m.field ? [m.field] : []))))];

  onMount(async () => {
    try {
      fetchParts().then((found) => (parts = found));
      const saved = await fetchSavedArtifact('retrofits');
      const content = (saved.content ?? {}) as Partial<RetrofitsDoc>;
      doc = { upgrade_order: content.upgrade_order ?? {}, packages: content.packages ?? [] };
      if (saved.exists) markSaved('retrofits', saved.savedAt);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load retrofits.';
    } finally {
      loading = false;
    }
  });

  function changed() {
    doc = doc;
    dirty = true;
  }

  function conditions(m: Measure): Condition[] {
    return !m.when ? [] : Array.isArray(m.when) ? m.when : [m.when];
  }

  function label(m: Measure): string {
    const target = m.to ?? Object.entries(m.map ?? {}).map(([a, b]) => `${a}→${b}`).join(', ');
    const when = conditions(m)
      .map((c) => `${c.field} ${c.in ? 'is' : 'is not'} ${(c.in ?? c.not_in ?? []).join(' or ')}`)
      .join(', ');
    const what = !m.part ? `${m.field} → ${target}` : m.to ? `${partLabel(m.part)} → ${m.to}` : `${partLabel(m.part)}: ${m.number} ${SHOWN[m.op as Shift]} ${m.value}`;
    return `${what}${when ? `  if ${when}` : ''}`;
  }

  async function pickPart(path: string) {
    draft = { ...draft, part: path, to: '', number: '' };
    const type = parts.find((part) => part.path === path)?.type;
    partRecords = [];
    partNumbers = [];
    if (!type) return;
    const [records, schema] = await Promise.all([
      fetchComponentRecords(type).catch(() => []),
      fetchComponentSchema(type).catch(() => null),
    ]);
    if (draft.part !== path) return;
    partRecords = records.map((record) => record.Name).filter((name) => !name.startsWith('auto_'));
    const numbers = (schema?.fields ?? []).filter((field) => field.kind === 'number').map((field) => field.name);
    partNumbers = type === 'ConstructionAssembly' ? [U, ...numbers] : numbers;
    draft = { ...draft, number: keyField(type) ?? partNumbers[0] ?? '' };
  }

  function addPackage() {
    let n = doc.packages.length + 1;
    while (doc.packages.some((p) => p.name === `Package ${n}`)) n += 1;
    doc.packages = [...doc.packages, { name: `Package ${n}`, measures: [] }];
    openAdd(doc.packages.length - 1);
    changed();
  }

  function openAdd(index: number) {
    adding = index;
    draft = { kind: 'field', field: fieldNames[0] ?? '', to: '', part: '', op: 'to', number: '', value: '', ifField: '', ifValue: '' };
  }

  $: draftReady =
    draft.kind === 'field'
      ? !!draft.field && !!draft.to
      : !!draft.part && (draft.op === 'to' ? !!draft.to : !!draft.number && draft.value !== '' && Number.isFinite(Number(draft.value)));

  function addMeasure() {
    if (adding === null || !draftReady) return;
    const measure: Measure =
      draft.kind === 'field'
        ? { field: draft.field, to: draft.to }
        : draft.op === 'to'
          ? { part: draft.part, to: draft.to }
          : { part: draft.part, number: draft.number, op: draft.op as Shift, value: Number(draft.value) };
    if (draft.ifField && draft.ifValue) measure.when = [{ field: draft.ifField, in: [draft.ifValue] }];
    doc.packages[adding].measures = [...doc.packages[adding].measures, measure];
    adding = null;
    changed();
  }

  function removeMeasure(p: number, m: number) {
    doc.packages[p].measures = doc.packages[p].measures.filter((_, i) => i !== m);
    changed();
  }

  function removePackage(p: number) {
    doc.packages = doc.packages.filter((_, i) => i !== p);
    if (adding === p) adding = null;
    changed();
  }

  function toggleOrder(field: string) {
    if (doc.upgrade_order[field]) {
      const { [field]: _, ...rest } = doc.upgrade_order;
      doc.upgrade_order = rest;
    } else {
      doc.upgrade_order = { ...doc.upgrade_order, [field]: [...(options[field] ?? [])] };
    }
    changed();
  }

  function move(field: string, index: number, delta: number) {
    const order = [...doc.upgrade_order[field]];
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    doc.upgrade_order = { ...doc.upgrade_order, [field]: order };
    changed();
  }

  async function save() {
    saving = true;
    error = null;
    try {
      const names = doc.packages.map((p) => p.name.trim());
      if (names.some((n) => !n) || new Set(names).size !== names.length) {
        throw new Error('Package names must be unique and not empty.');
      }
      if (names.includes('Baseline')) throw new Error('"Baseline" is reserved.');
      const file = await saveArtifact('retrofits', doc);
      markSaved('retrofits', file.modifiedAt);
      dirty = false;
      if (file.compile && !file.compile.ok) error = `Saved, but the model can't be built yet: ${file.compile.errors.join(' ')}`;
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
      <h1>Retrofits <Explain text={help.page} tip /></h1>
      <Explain text={help.page} />
      <p class="saved-line">{formatSavedAt($savedAt['retrofits'])}{dirty ? ' · unsaved changes' : ''}</p>
    </div>
    <div class="actions">
      <button type="button" class="btn" onclick={save} disabled={saving || !dirty} data-tour="retro-save">{saving ? 'Saving…' : 'Save'}</button>
    </div>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error" role="alert">{error}</p>{/if}

    {#if loading}
      <p class="hint">Loading…</p>
    {:else if fieldNames.length === 0}
      <WorkflowGuide
        title="Define building characteristics first"
        message="Each measure changes a building characteristic, e.g. Heating from oil to heat pump."
        actionLabel="Go to Building Characteristics"
        actionWorkflow="characteristics"
      />
    {:else}
      <div class="panel">
        <h2>Packages <Explain text={help.packages} tip /></h2>
        <Explain text={help.packages} />
        {#if doc.packages.length === 0}
          <div class="empty empty-box">
            <p>No packages yet. A package is a set of measures applied together, and is compared against the baseline.</p>
            <button type="button" class="btn" onclick={addPackage} data-tour="retro-add"><Icon name="plus" size={14} />Add package</button>
          </div>
        {/if}
        {#each doc.packages as pkg, p}
          <div class="package">
            <div class="package-head">
              <input class="name" bind:value={pkg.name} oninput={changed} aria-label="Package name" />
              <button type="button" class="btn btn-ghost btn-sm remove" title="Remove package" aria-label="Remove package" onclick={() => removePackage(p)}><Icon name="x" /></button>
            </div>
            <div class="chips" data-tour="retro-measure">
              {#each pkg.measures as measure, m}
                <span class="chip">
                  {label(measure)}
                  <button type="button" class="chip-x" title="Remove" aria-label="Remove measure" onclick={() => removeMeasure(p, m)}><Icon name="x" size={12} /></button>
                </span>
              {/each}
              {#if adding === p}
                <span class="add-row">
                  <span class="kind" role="radiogroup" aria-label="What the measure changes">
                    <button type="button" role="radio" aria-checked={draft.kind === 'field'} class:selected={draft.kind === 'field'} onclick={() => (draft = { ...draft, kind: 'field', to: '' })}>characteristic</button>
                    <button type="button" role="radio" aria-checked={draft.kind === 'part'} class:selected={draft.kind === 'part'} onclick={() => (draft = { ...draft, kind: 'part', to: '' })}>model part</button>
                  </span>
                  {#if draft.kind === 'field'}
                    <span class="pick">
                      <Select
                        value={draft.field}
                        options={fieldNames.map((name) => ({ value: name, label: name }))}
                        placeholder="characteristic"
                        ariaLabel="Characteristic to change"
                        onChange={(value) => (draft = { ...draft, field: value, to: '' })}
                      />
                    </span>
                    <Icon name="arrow-right" size={14} />
                    <span class="pick">
                      <Select
                        value={draft.to}
                        options={(options[draft.field] ?? []).map((opt) => ({ value: opt, label: opt }))}
                        placeholder="value"
                        ariaLabel="Change it to"
                        onChange={(value) => (draft = { ...draft, to: value })}
                      />
                    </span>
                  {:else}
                    <span class="pick">
                      <Select
                        value={draft.part}
                        options={parts.map((part) => ({ value: part.path, label: partLabel(part.path) }))}
                        placeholder="part"
                        ariaLabel="Model part to change"
                        onChange={pickPart}
                      />
                    </span>
                    {#if draft.op !== 'to'}
                      <span class="pick">
                        <Select
                          value={draft.number}
                          options={partNumbers.map((name) => ({ value: name, label: name }))}
                          placeholder="number"
                          ariaLabel="Number to change"
                          onChange={(value) => (draft = { ...draft, number: value })}
                        />
                      </span>
                    {/if}
                    <span class="pick">
                      <Select value={draft.op} options={ACTIONS} ariaLabel="How it changes" onChange={(value) => (draft = { ...draft, op: value })} />
                    </span>
                    {#if draft.op === 'to'}
                      <span class="pick">
                        <Select
                          value={draft.to}
                          options={partRecords.map((name) => ({ value: name, label: name }))}
                          placeholder="component"
                          ariaLabel="Replace with"
                          onChange={(value) => (draft = { ...draft, to: value })}
                        />
                      </span>
                    {:else}
                      <input class="amount" type="number" step="any" value={draft.value} aria-label="By how much" placeholder={draft.op === 'scale' ? '0.5' : ''}
                        oninput={(e) => (draft = { ...draft, value: (e.currentTarget as HTMLInputElement).value })} />
                    {/if}
                  {/if}
                  <span class="hint">if</span>
                  <span class="pick">
                    <Select
                      value={draft.ifField}
                      options={[
                        { value: '', label: 'always' },
                        ...fieldNames.map((name) => ({ value: name, label: name })),
                      ]}
                      ariaLabel="Only if"
                      onChange={(value) => (draft = { ...draft, ifField: value, ifValue: '' })}
                    />
                  </span>
                  {#if draft.ifField}
                    <span class="pick">
                      <Select
                        value={draft.ifValue}
                        options={(options[draft.ifField] ?? []).map((opt) => ({ value: opt, label: opt }))}
                        placeholder="is"
                        ariaLabel={`${draft.ifField} is`}
                        onChange={(value) => (draft = { ...draft, ifValue: value })}
                      />
                    </span>
                  {/if}
                  <button type="button" class="btn" onclick={addMeasure} disabled={!draftReady || (!!draft.ifField && !draft.ifValue)}>Add</button>
                  <button type="button" class="btn btn-ghost square" title="Cancel" aria-label="Cancel" onclick={() => (adding = null)}><Icon name="x" /></button>
                </span>
              {:else}
                <button type="button" class="btn btn-link" onclick={() => openAdd(p)}><Icon name="plus" size={14} />Add measure</button>
              {/if}
            </div>
          </div>
        {/each}
        {#if doc.packages.length > 0}
          <button type="button" class="btn btn-link" onclick={addPackage} data-tour="retro-add"><Icon name="plus" size={14} />Add package</button>
        {/if}
      </div>

      {#if usedFields.length > 0}
        <div class="panel">
          <h2>Never downgrade <Explain text={help.order} tip /></h2>
          <Explain text={help.order} />
          {#each usedFields as field}
            <div class="order-row">
              <label class="toggle">
                <input type="checkbox" checked={!!doc.upgrade_order[field]} onchange={() => toggleOrder(field)} />
                {field}
              </label>
              {#if doc.upgrade_order[field]}
                <span class="order">
                  {#each doc.upgrade_order[field] as opt, i}
                    <span class="step">
                      {#if i > 0}<button type="button" class="arrow" title="Move left (worse)" aria-label="Move {opt} left" onclick={() => move(field, i, -1)}><Icon name="chevron-left" size={14} /></button>{/if}
                      {opt}
                      {#if i < doc.upgrade_order[field].length - 1}<button type="button" class="arrow" title="Move right (better)" aria-label="Move {opt} right" onclick={() => move(field, i, 1)}><Icon name="chevron-right" size={14} /></button>{/if}
                    </span>
                    {#if i < doc.upgrade_order[field].length - 1}<span class="lt">&lt;</span>{/if}
                  {/each}
                </span>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</section>

<style>
  .workflow-header { flex-direction: row; justify-content: space-between; align-items: center; }
  .saved-line { margin-top: var(--space-1); color: var(--text-faint); font-size: var(--text-xs); }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-3); }
  .workflow-content { max-width: 960px; }
  .package { display: flex; flex-direction: column; gap: var(--space-2); padding-bottom: var(--space-4); border-bottom: 1px solid var(--border); }
  .package-head { display: flex; align-items: center; gap: var(--space-3); }
  .name { min-width: 200px; font-size: var(--text-md); font-weight: 600; border-color: transparent; }
  .name:hover, .name:focus { border-color: var(--border-strong); }
  .remove { margin-left: auto; }
  .chips { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; }
  .chip { display: inline-flex; align-items: center; gap: var(--space-1); background: var(--surface-3); border-radius: var(--radius-sm); padding: var(--space-1) var(--space-1) var(--space-1) var(--space-3); font-size: var(--text-sm); }
  .chip-x, .arrow { display: inline-flex; border: none; background: transparent; color: var(--text-faint); cursor: pointer; padding: 0 var(--space-1); }
  .chip-x:hover, .arrow:hover { color: var(--text); }
  .add-row { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--text-muted); }
  .add-row .pick { min-width: 130px; }
  .add-row .amount { width: 80px; }
  .kind { display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); overflow: hidden; }
  .kind button { min-height: var(--control-h-sm); padding: 0 var(--space-2); border: none; background: var(--surface); color: var(--text-2); font-size: var(--text-xs); cursor: pointer; }
  .kind button + button { border-left: 1px solid var(--border-strong); }
  .kind button.selected { background: var(--accent-soft); color: var(--text); font-weight: 600; }
  .square { padding: 0; width: var(--control-h); }
  .btn-link { align-self: flex-start; }
  .order-row { display: flex; align-items: center; gap: var(--space-4); font-size: var(--text-sm); }
  .toggle { display: inline-flex; align-items: center; gap: var(--space-2); min-width: 180px; }
  .order { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }
  .step { display: inline-flex; align-items: center; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); padding: 2px var(--space-1); }
  .lt { color: var(--text-faint); }
</style>
