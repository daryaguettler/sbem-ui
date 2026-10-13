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
      <h1>Retrofits</h1>
      <p class="subtitle">Bundle upgrades into packages, e.g. “oil boiler → heat pump where built before 1975”.</p>
      <p class="saved-line">{formatSavedAt($savedAt['retrofits'])}{dirty ? ' · unsaved changes' : ''}</p>
    </div>
    <div class="actions">
      {#if runnerAvailable}
        <button type="button" class="secondary" onclick={runPreview} disabled={previewing || doc.packages.length === 0}>
          {previewing ? 'Previewing…' : 'Preview'}
        </button>
      {/if}
      <button type="button" onclick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error">{error}</p>{/if}
    {#if !loading && !runnerAvailable}
      <RunnerNotice feature="Previewing how many buildings each package changes" />
    {/if}

    {#if loading}
      <p class="muted">Loading…</p>
    {:else if fieldNames.length === 0}
      <WorkflowGuide
        title="Define semantic fields first"
        message="Each measure changes a semantic field, e.g. Heating from oil to heat pump."
        actionLabel="Go to Semantic Fields"
        actionWorkflow="semantic-fields"
      />
    {:else}
      <div class="panel">
        <h2>Packages</h2>
        {#if doc.packages.length === 0}
          <div class="empty">
            <p>No packages yet. A package is a set of measures applied together, and is compared against the baseline.</p>
            <button type="button" onclick={addPackage}>+ Add package</button>
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
                  <select bind:value={draft.field} onchange={() => (draft.to = '')}>
                    {#each fieldNames as name}<option value={name}>{name}</option>{/each}
                  </select>
                  →
                  <select bind:value={draft.to}>
                    <option value="" disabled>option</option>
                    {#each options[draft.field] ?? [] as opt}<option value={opt}>{opt}</option>{/each}
                  </select>
                  <span class="muted">if</span>
                  <select bind:value={draft.ifField} onchange={() => (draft.ifValue = '')}>
                    <option value="">always</option>
                    {#each fieldNames as name}<option value={name}>{name}</option>{/each}
                  </select>
                  {#if draft.ifField}
                    <select bind:value={draft.ifValue}>
                      <option value="" disabled>is</option>
                      {#each options[draft.ifField] ?? [] as opt}<option value={opt}>{opt}</option>{/each}
                    </select>
                  {/if}
                  <button type="button" class="small" onclick={addMeasure} disabled={!draft.to || (!!draft.ifField && !draft.ifValue)}>Add</button>
                  <button type="button" class="icon" title="Cancel" onclick={() => (adding = null)}>×</button>
                </span>
              {:else}
                <button type="button" class="link" onclick={() => openAdd(p)}>+ Add measure</button>
              {/if}
            </div>
          </div>
        {/each}
        {#if doc.packages.length > 0}
          <button type="button" class="link" onclick={addPackage}>+ Add package</button>
        {/if}
      </div>

      {#if usedFields.length > 0}
        <div class="panel">
          <h2>Never downgrade</h2>
          <p class="muted">Tick a field and order its options from worst (left) to best (right); measures then only move a building rightwards.</p>
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
  .workflow { display: flex; flex-direction: column; height: 100%; }
  .workflow-header {
    padding: 24px 32px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .workflow-header h1 { margin: 0 0 4px; font-size: 24px; }
  .subtitle { margin: 0; color: var(--text-muted); font-size: 14px; }
  .saved-line { margin: 2px 0 0; color: var(--text-faint); font-size: 12px; }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; color: var(--text-muted); font-size: 14px; }
  .actions { display: flex; gap: 8px; }
  .workflow-content { padding: 32px; display: flex; flex-direction: column; gap: 20px; max-width: 960px; }
  .panel { border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .panel h2 { margin: 0; font-size: 15px; }
  .package { display: flex; flex-direction: column; gap: 8px; padding-bottom: 14px; border-bottom: 1px solid var(--surface-3); }
  .package-head { display: flex; align-items: center; gap: 10px; }
  .name { font-size: 15px; font-weight: 600; border: 1px solid transparent; border-radius: 6px; padding: 4px 6px; min-width: 200px; }
  .name:hover, .name:focus { border-color: var(--border); outline: none; }
  .share { font-size: 12px; color: var(--accent); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chip { display: inline-flex; align-items: center; gap: 4px; background: var(--surface-3); border-radius: 999px; padding: 4px 6px 4px 12px; font-size: 13px; }
  .chip-x, .icon, .arrow { border: none; background: transparent; color: var(--text-faint); cursor: pointer; font-size: 14px; padding: 0 4px; }
  .chip-x:hover, .icon:hover, .arrow:hover { color: var(--text); }
  .icon { margin-left: auto; }
  .add-row { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .add-row .icon { margin-left: 0; }
  select { border: 1px solid var(--border); border-radius: 6px; padding: 4px 6px; font-size: 13px; background: var(--surface); }
  .link { border: none; background: transparent; color: var(--accent); cursor: pointer; font-size: 13px; padding: 4px 0; text-align: left; }
  .order-row { display: flex; align-items: center; gap: 16px; font-size: 13px; }
  .toggle { display: inline-flex; align-items: center; gap: 6px; min-width: 180px; }
  .order { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; }
  .step { display: inline-flex; align-items: center; background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px; padding: 2px 4px; }
  .lt { color: var(--text-faint); }
  button { border: none; border-radius: 8px; background: var(--accent); color: var(--on-accent); padding: 8px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
  button.secondary { background: var(--surface); color: var(--text); border: 1px solid var(--border); }
  button.small { padding: 4px 10px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .error { color: var(--err-text); font-size: 13px; margin: 0; }
</style>
