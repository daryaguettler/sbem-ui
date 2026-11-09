<script lang="ts">
  /**
   * One schedule as one form: day profiles you draw, week patterns that pick a profile per
   * weekday, and months that pick a week pattern. Saved as epinterface Day/Week/Year records
   * (the server names them "{schedule}__{profile}"). Same props as SchemaForm, so it drops in
   * wherever a Year record is created or edited.
   */
  import { onMount } from 'svelte';
  import { fetchSchedule, saveSchedule } from '../../api/componentLibrary';
  import { fetchSavedArtifact } from '../../api/artifacts';
  import {
    CATEGORIES,
    DAYS,
    MONTHS,
    PRESETS,
    clampToLimit,
    defaultDraft,
    freshName,
    parametric,
    parsePasted,
    removeProfile,
    removeWeek,
    renameProfile,
    renameWeek,
    type Limit,
    type Parametric,
    type ScheduleDraft,
  } from '../../utils/schedules';
  import ScheduleChart from './ScheduleChart.svelte';
  import Select from '../Select.svelte';
  import Icon from '../Icon.svelte';

  let {
    mode,
    name = null,
    presetName = '',
    copyFrom = null,
    trail = [],
    onSaved,
    onCancel,
  }: {
    componentType?: string;
    mode: 'create' | 'edit';
    name?: string | null;
    presetName?: string;
    copyFrom?: string | null;
    trail?: string[];
    onSaved: (record: Record<string, unknown>) => void;
    onCancel: () => void;
  } = $props();

  const uid = $props.id();
  let draft = $state<ScheduleDraft>(defaultDraft());
  let profile = $state('Weekday');
  let loading = $state(true);
  let saving = $state(false);
  let error = $state<string | null>(null);
  let tool = $state<'none' | 'parametric' | 'paste'>('none');
  let params = $state<Parametric>({ on: 8, off: 18, base: 0.1, peak: 1, ramp: 1 });
  let pasted = $state('');
  let showVariability = $state(false);
  let variabilityConfig = $state<Record<string, unknown> | null>(null);
  let overlays = $state<number[][]>([]);

  const profileNames = $derived(Object.keys(draft.profiles));
  const profileOptions = $derived(profileNames.map((p) => ({ value: p, label: p })));
  const weekNames = $derived(Object.keys(draft.weeks));
  const presetOptions = $derived(
    Object.entries(PRESETS)
      .filter(([, preset]) => preset.limit === draft.Limit)
      .map(([label]) => ({ value: label, label }))
  );

  onMount(async () => {
    const source = mode === 'edit' ? name : copyFrom;
    try {
      if (source) {
        const loaded = await fetchSchedule(source);
        draft = mode === 'edit' ? loaded : { ...loaded, Name: presetName || `${source} copy` };
      } else {
        draft = defaultDraft(presetName);
      }
      profile = Object.keys(draft.profiles)[0];
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load the schedule.';
    } finally {
      loading = false;
    }
  });

  function setValues(values: number[]) {
    draft.profiles[profile] = clampToLimit(values, draft.Limit);
  }

  function setLimit(limit: Limit) {
    draft.Limit = limit;
    for (const key of profileNames) draft.profiles[key] = clampToLimit(draft.profiles[key], limit);
  }

  /** Apply a rename/remove helper; it returns null when the change isn't allowed. */
  function apply(next: ScheduleDraft | null, refused: string): boolean {
    if (!next) {
      error = refused;
      return false;
    }
    draft = next;
    error = null;
    return true;
  }

  function addProfile() {
    const added = freshName('Profile', draft.profiles);
    draft.profiles[added] = [...draft.profiles[profile]];
    profile = added;
  }

  function addWeek() {
    draft.weeks[freshName('Pattern', draft.weeks)] = { ...draft.weeks[weekNames[0]] };
  }

  /** Clicking a month moves it to the next week pattern. */
  function cycleMonth(month: (typeof MONTHS)[number]) {
    draft.months[month] = weekNames[(weekNames.indexOf(draft.months[month]) + 1) % weekNames.length];
  }

  function applyPaste() {
    const result = parsePasted(pasted);
    if (typeof result === 'string') {
      error = result;
      return;
    }
    setValues(result);
    pasted = '';
    tool = 'none';
    error = null;
  }

  async function submit() {
    saving = true;
    error = null;
    try {
      const saved = await saveSchedule($state.snapshot(draft), mode === 'edit' ? name : null);
      onSaved({ Name: saved.Name });
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to save.';
    } finally {
      saving = false;
    }
  }

  // Sampled buildings' copies of the profile on screen, from the saved schedule-variability settings.
  $effect(() => {
    if (!showVariability) {
      overlays = [];
      return;
    }
    const body = JSON.stringify({
      config: variabilityConfig,
      limit: draft.Limit,
      values: draft.profiles[profile],
      day_name: `${draft.Name}__${profile}`,
      n: 20,
    });
    if (!variabilityConfig) {
      fetchSavedArtifact('schedule-variability')
        .then((saved) => (variabilityConfig = (saved.content ?? {}) as Record<string, unknown>))
        .catch(() => (error = "Couldn't load the schedule variability settings."));
      return;
    }
    const timer = setTimeout(async () => {
      const response = await fetch('/api/schedule-variability/preview-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      const payload = await response.json().catch(() => null);
      if (response.ok) overlays = payload.samples;
      else error = typeof payload?.detail === 'string' ? payload.detail : 'Variability preview failed.';
    }, 300);
    return () => clearTimeout(timer);
  });
</script>

{#if loading}
  <p class="hint">Loading schedule…</p>
{:else}
  {#if trail.length > 0}
    <nav class="crumbs" aria-label="Nested record">
      <button type="button" class="btn btn-ghost btn-sm" onclick={onCancel}><Icon name="arrow-left" size={14} />Back</button>
      <span class="hint">{trail.join(' › ')} › <strong>New schedule</strong></span>
    </nav>
  {/if}

  <form class="schedule" onsubmit={(event) => { event.preventDefault(); submit(); }}>
    <div class="field-grid head">
      <label class="field">Name <input bind:value={draft.Name} required /></label>
      <label class="field">
        Used for
        <Select value={draft.Type} options={CATEGORIES.map((c) => ({ value: c, label: c }))} onChange={(v) => (draft.Type = v as ScheduleDraft['Type'])} />
      </label>
      <div class="field">
        Values
        <div class="segmented" role="group" aria-label="Value type">
          {#each ['Fraction', 'Temperature', 'AnyNumber'] as const as limit}
            <button type="button" aria-pressed={draft.Limit === limit} onclick={() => setLimit(limit)}>
              {limit === 'Fraction' ? '0–1' : limit === 'Temperature' ? '°C' : 'Any'}
            </button>
          {/each}
        </div>
      </div>
    </div>

    <section>
      <h3>Day profiles</h3>
      <div class="tabs" role="tablist" aria-label="Day profiles">
        {#each profileNames as p}
          <button type="button" role="tab" aria-selected={p === profile} class:active={p === profile} onclick={() => (profile = p)}>{p}</button>
        {/each}
        <button type="button" class="btn btn-ghost btn-sm" onclick={addProfile}><Icon name="plus" size={14} />Profile</button>
      </div>

      <div class="row">
        <label class="field grow">
          Profile name
          <input
            value={profile}
            onchange={(e) => {
              const to = e.currentTarget.value.trim();
              if (apply(renameProfile(draft, profile, to), `Can't rename to "${to}": the name is taken, empty, or contains "__".`)) profile = to;
              else e.currentTarget.value = profile;
            }}
          />
        </label>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          disabled={profileNames.length < 2}
          onclick={() => {
            if (apply(removeProfile(draft, profile), `A week pattern still uses "${profile}"; pick another profile there first.`)) profile = Object.keys(draft.profiles)[0];
          }}
        >Remove</button>
      </div>

      <ScheduleChart values={draft.profiles[profile]} limit={draft.Limit} {overlays} label={profile} onChange={setValues} />

      <div class="toolbar">
        <span class="pick">
          <Select value="" placeholder="Preset…" ariaLabel="Apply a preset" options={presetOptions} onChange={(v) => setValues([...PRESETS[v].values])} />
        </span>
        {#if profileNames.length > 1}
          <span class="pick">
            <Select
              value=""
              placeholder="Copy from…"
              ariaLabel="Copy values from another profile"
              options={profileOptions.filter((o) => o.value !== profile)}
              onChange={(v) => setValues([...draft.profiles[v]])}
            />
          </span>
        {/if}
        <button type="button" class="btn btn-secondary btn-sm" aria-pressed={tool === 'parametric'} onclick={() => (tool = tool === 'parametric' ? 'none' : 'parametric')}>On/off hours</button>
        <button type="button" class="btn btn-secondary btn-sm" aria-pressed={tool === 'paste'} onclick={() => (tool = tool === 'paste' ? 'none' : 'paste')}>Paste 24 values</button>
        <label class="hint toggle"><input type="checkbox" bind:checked={showVariability} /> Show variability</label>
      </div>

      {#if tool === 'parametric'}
        <div class="field-grid params">
          <label class="field">On at (h)<input type="number" min="0" max="23" bind:value={params.on} /></label>
          <label class="field">Off at (h)<input type="number" min="0" max="24" bind:value={params.off} /></label>
          <label class="field">Base<input type="number" step="any" bind:value={params.base} /></label>
          <label class="field">Peak<input type="number" step="any" bind:value={params.peak} /></label>
          <label class="field">Ramp (h)<input type="number" min="0" max="6" bind:value={params.ramp} /></label>
          <button type="button" class="btn btn-sm" onclick={() => setValues(parametric(params))}>Apply</button>
        </div>
      {:else if tool === 'paste'}
        <label class="field">
          <span class="field-hint">24 numbers, hour 0 first: a column copied from a spreadsheet, or separated by commas or spaces.</span>
          <textarea rows="3" bind:value={pasted}></textarea>
        </label>
        <button type="button" class="btn btn-sm" onclick={applyPaste}>Apply</button>
      {/if}
      {#if showVariability}
        <p class="hint">Faint lines: 20 buildings' copies of this profile, using the settings on the Schedule variability tab.</p>
      {/if}
    </section>

    <section>
      <h3>Weekly patterns</h3>
      <div class="table-wrap">
        <table class="data-table weeks">
          <thead>
            <tr><th>Pattern</th>{#each DAYS as d}<th>{d.slice(0, 3)}</th>{/each}<th><span class="visually-hidden">Actions</span></th></tr>
          </thead>
          <tbody>
            {#each weekNames as week (week)}
              <tr>
                <td>
                  <input
                    class="input-sm"
                    aria-label="Pattern name"
                    value={week}
                    onchange={(e) => {
                      const to = e.currentTarget.value.trim();
                      if (!apply(renameWeek(draft, week, to), `Can't rename to "${to}": the name is taken, empty, or contains "__".`)) e.currentTarget.value = week;
                    }}
                  />
                </td>
                {#each DAYS as d}
                  <td>
                    <Select value={draft.weeks[week][d]} ariaLabel="{week}, {d}" options={profileOptions} onChange={(v) => (draft.weeks[week][d] = v)} />
                  </td>
                {/each}
                <td>
                  <button type="button" class="btn btn-ghost btn-sm" aria-label="Remove {week}" disabled={weekNames.length < 2}
                    onclick={() => apply(removeWeek(draft, week), `Months still use "${week}"; move them to another pattern first.`)}
                  ><Icon name="x" size={14} /></button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <button type="button" class="btn btn-ghost btn-sm" onclick={addWeek}><Icon name="plus" size={14} />Pattern (e.g. summer)</button>
    </section>

    <section>
      <h3>Months</h3>
      <p class="hint" id="{uid}-months">Click a month to move it to the next weekly pattern.</p>
      <div class="months" aria-describedby="{uid}-months">
        {#each MONTHS as month}
          <button type="button" class="month" onclick={() => cycleMonth(month)} aria-label="{month}: {draft.months[month]}" disabled={weekNames.length < 2}>
            <strong>{month.slice(0, 3)}</strong><span>{draft.months[month]}</span>
          </button>
        {/each}
      </div>
    </section>

    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <div class="actions">
      <button type="button" class="btn btn-secondary" onclick={onCancel}>Cancel</button>
      <button type="submit" class="btn" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  </form>
{/if}

<style>
  .schedule { display: flex; flex-direction: column; gap: var(--space-5); }
  .head { --field-min: 140px; }
  .params { --field-min: 80px; align-items: end; }
  h3 { margin: 0 0 var(--space-2); font-size: var(--text-md); }
  .crumbs { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
  .tabs { display: flex; flex-wrap: wrap; align-items: center; margin-bottom: var(--space-3); }
  .row, .toolbar { display: flex; align-items: end; gap: var(--space-2); flex-wrap: wrap; margin: var(--space-2) 0; }
  .grow { flex: 1; }
  .pick { width: 150px; }
  .toggle { display: inline-flex; align-items: center; gap: var(--space-1); }
  .table-wrap { overflow-x: auto; }
  .weeks td, .weeks th { padding: var(--space-1); }
  .weeks input { width: 90px; }
  .weeks td :global(button) { min-width: 72px; }
  .months { display: grid; grid-template-columns: repeat(6, 1fr); gap: var(--space-1); }
  .month { display: flex; flex-direction: column; align-items: center; padding: var(--space-1); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); font-size: var(--text-xs); }
  .month span { color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .month:disabled { cursor: default; opacity: 1; }
  textarea { width: 100%; font-family: var(--font-mono, monospace); }
</style>
