<script lang="ts">
  /**
   * Retrofit packages (retrofits.yaml): each package is a list of measures that set a
   * semantic field to a better option, optionally only where another field has a given
   * value. "Never downgrade" orders a field's options so a measure only ever moves a
   * building up. Preview asks the runner how many draws each package changes.
   */
  import { onMount } from 'svelte';
  import RunnerNotice from '../components/RunnerNotice.svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import { fetchSavedArtifact, formatSavedAt, saveArtifact } from '../api/artifacts';
  import { fetchRunnerStatus, runJob } from '../api/runner';
  import { markSaved, savedAt } from '../stores/projectArtifacts';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import Explain from '../components/Explain.svelte';
  import Select from '../components/Select.svelte';
  import { HELP } from '../help';
  const help = HELP.retrofits;

  interface Condition {
    field: string;
    in?: string[];
    not_in?: string[];
  }
  interface Measure {
    field: string;
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
  interface PreviewRow {
    name: string;
    share_changed: number;
  }

  let doc: RetrofitsDoc = { upgrade_order: {}, packages: [] };
  let loading = true;
  let saving = false;
  let dirty = false;
  let error: string | null = null;
  let runnerAvailable = false;
  let previewing = false;
  let preview: Record<string, number> = {};

  /** The package whose "+ measure" row is open, and that row's draft. */
  let adding: number | null = null;
  let draft = { field: '', to: '', ifField: '', ifValue: '' };

  $: options = Object.fromEntries(
    $semanticFieldsStore.fields
      .filter((f) => f.options && f.options.length > 0)
      .map((f) => [f.name, f.options])
  ) as Record<string, string[]>;
  $: fieldNames = Object.keys(options);
  $: usedFields = [...new Set(doc.packages.flatMap((p) => p.measures.map((m) => m.field)))];

  onMount(async () => {
    try {
      const saved = await fetchSavedArtifact('retrofits');
      const content = (saved.content ?? {}) as Partial<RetrofitsDoc>;
      doc = { upgrade_order: content.upgrade_order ?? {}, packages: content.packages ?? [] };
      if (saved.exists) markSaved('retrofits', saved.savedAt);
      runnerAvailable = (await fetchRunnerStatus()).available;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load retrofits.';
    } finally {
      loading = false;
    }
  });

  function changed() {
    doc = doc;
    dirty = true;
    preview = {};
  }

  function conditions(m: Measure): Condition[] {
    return !m.when ? [] : Array.isArray(m.when) ? m.when : [m.when];
  }

  function label(m: Measure): string {
    const target = m.to ?? Object.entries(m.map ?? {}).map(([a, b]) => `${a}→${b}`).join(', ');
    const when = conditions(m)
      .map((c) => `${c.field} ${c.in ? 'is' : 'is not'} ${(c.in ?? c.not_in ?? []).join(' or ')}`)
      .join(', ');
    return `${m.field} → ${target}${when ? `  if ${when}` : ''}`;
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
    draft = { field: fieldNames[0] ?? '', to: '', ifField: '', ifValue: '' };
  }

  function addMeasure() {
    if (adding === null || !draft.field || !draft.to) return;
    const measure: Measure = { field: draft.field, to: draft.to };
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
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to save.';
    } finally {
      saving = false;
    }
  }

  async function runPreview() {
    if (dirty) await save();
    if (error) return;
    previewing = true;
    try {
      const result = await runJob<{ errors: string[]; packages: PreviewRow[] }>('retrofit-preview');
      if (result.errors.length) throw new Error(result.errors.join('; '));
      preview = Object.fromEntries(result.packages.map((r) => [r.name, r.share_changed]));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Preview failed.';
    } finally {
      previewing = false;
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
      {#if runnerAvailable}
        <button type="button" class="btn btn-secondary" onclick={runPreview} disabled={previewing || doc.packages.length === 0}>
          {previewing ? 'Previewing…' : 'Preview'}
        </button>
      {/if}
      <button type="button" class="btn" onclick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if !loading && !runnerAvailable}
      <RunnerNotice feature="Previewing how many buildings each package changes" />
    {/if}

    {#if loading}
      <p class="muted">Loading…</p>
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
          <div class="empty">
            <p>No packages yet. A package is a set of measures applied together, and is compared against the baseline.</p>
            <button type="button" class="btn" onclick={addPackage}>+ Add package</button>
          </div>
        {/if}
        {#each doc.packages as pkg, p}
          <div class="package">
            <div class="package-head">
              <input class="name" bind:value={pkg.name} oninput={changed} aria-label="Package name" />
              {#if preview[pkg.name] !== undefined}
                <span class="share">{Math.round(preview[pkg.name] * 100)}% changed</span>
              {/if}
              <button type="button" class="icon" title="Remove package" onclick={() => removePackage(p)}>×</button>
            </div>
            <div class="chips">
              {#each pkg.measures as measure, m}
                <span class="chip">
                  {label(measure)}
                  <button type="button" class="chip-x" title="Remove" onclick={() => removeMeasure(p, m)}>×</button>
                </span>
              {/each}
              {#if adding === p}
                <span class="add-row">
                  <span class="pick">
                    <Select
                      value={draft.field}
                      options={fieldNames.map((name) => ({ value: name, label: name }))}
                      placeholder="characteristic"
                      ariaLabel="Characteristic to change"
                      onChange={(value) => (draft = { ...draft, field: value, to: '' })}
                    />
                  </span>
                  →
                  <span class="pick">
                    <Select
                      value={draft.to}
                      options={(options[draft.field] ?? []).map((opt) => ({ value: opt, label: opt }))}
                      placeholder="value"
                      ariaLabel="Change it to"
                      onChange={(value) => (draft = { ...draft, to: value })}
                    />
                  </span>
                  <span class="muted">if</span>
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
                  <button type="button" class="btn btn-sm" onclick={addMeasure} disabled={!draft.to || (!!draft.ifField && !draft.ifValue)}>Add</button>
                  <button type="button" class="icon" title="Cancel" onclick={() => (adding = null)}>×</button>
                </span>
              {:else}
                <button type="button" class="btn btn-link" onclick={() => openAdd(p)}>+ Add measure</button>
              {/if}
            </div>
          </div>
        {/each}
        {#if doc.packages.length > 0}
          <button type="button" class="btn btn-link" onclick={addPackage}>+ Add package</button>
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
                      {#if i > 0}<button type="button" class="arrow" title="Move left (worse)" aria-label="Move {opt} left" onclick={() => move(field, i, -1)}>‹</button>{/if}
                      {opt}
                      {#if i < doc.upgrade_order[field].length - 1}<button type="button" class="arrow" title="Move right (better)" aria-label="Move {opt} right" onclick={() => move(field, i, 1)}>›</button>{/if}
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
  .saved-line { margin: 2px 0 0; color: var(--text-faint); font-size: 12px; }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; color: var(--text-muted); font-size: 14px; }
  .actions { display: flex; gap: 8px; }
  .workflow-content { max-width: 960px; }
  .package { display: flex; flex-direction: column; gap: 8px; padding-bottom: 14px; border-bottom: 1px solid var(--surface-3); }
  .package-head { display: flex; align-items: center; gap: 10px; }
  .name { font-size: 15px; font-weight: 600; border: 1px solid transparent; border-radius: var(--radius); padding: 4px 6px; min-width: 200px; }
  .name:hover, .name:focus { border-color: var(--border); outline: none; }
  .share { font-size: 12px; color: var(--accent); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chip { display: inline-flex; align-items: center; gap: 4px; background: var(--surface-3); border-radius: var(--radius-sm); padding: 4px 6px 4px 12px; font-size: 13px; }
  .chip-x, .icon, .arrow { border: none; background: transparent; color: var(--text-faint); cursor: pointer; font-size: 14px; padding: 0 4px; }
  .chip-x:hover, .icon:hover, .arrow:hover { color: var(--text); }
  .icon { margin-left: auto; }
  .add-row { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .add-row .icon { margin-left: 0; }
  .add-row .pick { min-width: 130px; }
  .btn-link { align-self: flex-start; }
  .order-row { display: flex; align-items: center; gap: 16px; font-size: 13px; }
  .toggle { display: inline-flex; align-items: center; gap: 6px; min-width: 180px; }
  .order { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; }
  .step { display: inline-flex; align-items: center; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); padding: 2px 4px; }
  .lt { color: var(--text-faint); }
  .muted { color: var(--text-muted); font-size: 13px; }
</style>
