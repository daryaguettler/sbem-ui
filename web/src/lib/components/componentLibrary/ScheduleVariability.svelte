<script lang="ts">
  /**
   * Schedule variability (schedule-variability.yaml, globi's schedule_variability_config):
   * seeded per-building noise on the library's schedules, so buildings sharing a SpaceUse
   * don't all run identical profiles. Strengths can differ per value of one semantic field.
   * The preview runs globi's own perturbation on a SpaceUse for 20 synthetic buildings.
   */
  import { onMount } from 'svelte';
  import { fetchSavedArtifact, formatSavedAt, saveArtifact } from '../../api/artifacts';
  import { fetchComponentRecords } from '../../api/componentLibrary';
  import { markSaved, savedAt } from '../../stores/projectArtifacts';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import Select from '../Select.svelte';

  type ParamKey =
    | 'time_shift_std_h'
    | 'intensity_cv'
    | 'hourly_noise_std'
    | 'hourly_noise_autocorr'
    | 'setpoint_offset_std_c';
  type Params = Record<ParamKey, number>;
  interface Doc {
    seed: number;
    semantic_field: string | null;
    default: Params;
    by_value: Record<string, Partial<Params>>;
  }
  interface Preview {
    base: Record<string, number[]>;
    samples: Array<{ curves: Record<string, number[]>; draws: Record<string, number> }>;
  }

  const COLUMNS: Array<{ key: ParamKey; label: string; step: number; max: number }> = [
    { key: 'time_shift_std_h', label: 'Time shift σ (h)', step: 0.25, max: 6 },
    { key: 'intensity_cv', label: 'Intensity CV', step: 0.05, max: 2 },
    { key: 'hourly_noise_std', label: 'Hourly noise σ', step: 0.01, max: 0.5 },
    { key: 'hourly_noise_autocorr', label: 'Noise autocorr.', step: 0.05, max: 0.95 },
    { key: 'setpoint_offset_std_c', label: 'Setpoint σ (°C)', step: 0.25, max: 5 },
  ];
  const ZERO: Params = {
    time_shift_std_h: 0,
    intensity_cv: 0,
    hourly_noise_std: 0,
    hourly_noise_autocorr: 0.7,
    setpoint_offset_std_c: 0,
  };
  const W = 480;
  const H = 160;

  let doc = $state<Doc>({ seed: 0, semantic_field: null, default: { ...ZERO }, by_value: {} });
  let loading = $state(true);
  let saving = $state(false);
  let dirty = $state(false);
  let error = $state<string | null>(null);
  let spaceUses = $state<string[]>([]);
  let spaceUse = $state('');
  let previewValue = $state('');
  let load = $state<'occupancy' | 'equipment'>('occupancy');
  let preview = $state<Preview | null>(null);

  let options = $derived(
    Object.fromEntries(
      $semanticFieldsStore.fields.filter((f) => f.options?.length).map((f) => [f.name, f.options])
    ) as Record<string, string[]>
  );
  let rows = $derived(doc.semantic_field ? (options[doc.semantic_field] ?? []) : []);
  let yMax = $derived(
    preview
      ? Math.max(1, ...preview.base[load], ...preview.samples.flatMap((s) => s.curves[load]))
      : 1
  );
  let shifts = $derived(preview?.samples.map((s) => s.draws['feature.schedule_variability.time_shift_h']) ?? []);

  onMount(async () => {
    try {
      const saved = await fetchSavedArtifact('schedule-variability');
      const content = (saved.content ?? {}) as Partial<Doc>;
      doc = {
        seed: content.seed ?? 0,
        semantic_field: content.semantic_field ?? null,
        default: { ...ZERO, ...(content.default ?? {}) },
        by_value: content.by_value ?? {},
      };
      if (saved.exists) markSaved('schedule-variability', saved.savedAt);
      spaceUses = (await fetchComponentRecords('SpaceUse')).map((r) => r.Name);
      spaceUse = spaceUses[0] ?? '';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load schedule variability.';
    } finally {
      loading = false;
    }
  });

  function setField(field: string) {
    // overrides are keyed by the old field's values, so they no longer apply
    doc.semantic_field = field || null;
    doc.by_value = {};
    previewValue = '';
    dirty = true;
  }

  function setOverride(value: string, key: ParamKey, raw: string) {
    const { [key]: _, ...rest } = doc.by_value[value] ?? {};
    const next = raw === '' ? rest : { ...rest, [key]: Number(raw) };
    const { [value]: __, ...others } = doc.by_value;
    doc.by_value = Object.keys(next).length ? { ...others, [value]: next } : others;
    dirty = true;
  }

  function path(values: number[]): string {
    return values.map((v, h) => `${h ? 'L' : 'M'}${(h * W) / 23},${H - (v / yMax) * (H - 10)}`).join(' ');
  }

  async function save() {
    saving = true;
    error = null;
    try {
      const file = await saveArtifact('schedule-variability', $state.snapshot(doc));
      markSaved('schedule-variability', file.modifiedAt);
      dirty = false;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to save.';
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    const body = JSON.stringify({
      config: $state.snapshot(doc),
      space_use: spaceUse,
      value: previewValue || null,
      n: 20,
    });
    if (!spaceUse) return;
    const timer = setTimeout(async () => {
      const response = await fetch('/api/schedule-variability/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        error = typeof payload?.detail === 'string' ? payload.detail : 'Preview failed.';
        return;
      }
      error = null;
      preview = payload;
    }, 300);
    return () => clearTimeout(timer);
  });
</script>

<section class="variability">
  <div class="section-head">
    <div>
      <p class="hint intro">Give each building its own seeded variation, so buildings sharing a schedule don't all switch on at once. globi applies it in batch runs (<code>schedule_variability_config</code>).</p>
      <p class="saved-line">{formatSavedAt($savedAt['schedule-variability'])}{dirty ? ' · unsaved changes' : ''}</p>
    </div>
    <button type="button" class="btn" onclick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</button>
  </div>

    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if loading}
      <p class="hint">Loading…</p>
    {:else}
      <div class="panel">
        <div class="field-grid settings">
          <label class="field">Seed <input type="number" min="0" step="1" bind:value={doc.seed} oninput={() => (dirty = true)} /></label>
          <label class="field">
            Vary by
            <Select
              value={doc.semantic_field ?? ''}
              options={[{ value: '', label: 'Nothing' }, ...Object.keys(options).map((name) => ({ value: name, label: name }))]}
              onChange={setField}
            />
          </label>
        </div>
        <table class="data-table">
          <thead>
            <tr><th></th>{#each COLUMNS as col}<th class="num">{col.label}</th>{/each}</tr>
          </thead>
          <tbody>
            <tr>
              <td>Default</td>
              {#each COLUMNS as col}
                <td class="num">
                  <input class="input-sm" type="number" min="0" max={col.max} step={col.step} bind:value={doc.default[col.key]} oninput={() => (dirty = true)} />
                </td>
              {/each}
            </tr>
            {#each rows as value}
              <tr>
                <td>{value}</td>
                {#each COLUMNS as col}
                  <td class="num">
                    <input
                      class="input-sm"
                      type="number"
                      min="0"
                      max={col.max}
                      step={col.step}
                      placeholder={String(doc.default[col.key])}
                      value={doc.by_value[value]?.[col.key] ?? ''}
                      oninput={(e) => setOverride(value, col.key, e.currentTarget.value)}
                    />
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
        {#if rows.length}<p class="hint">Empty cells use the default.</p>{/if}
      </div>

      <div class="panel">
        <div class="controls">
          <h2>Preview</h2>
          {#if spaceUses.length}
            <span class="pick">
              <Select
                value={spaceUse}
                options={spaceUses.map((name) => ({ value: name, label: name }))}
                ariaLabel="SpaceUse"
                onChange={(value) => (spaceUse = value)}
              />
            </span>
            {#if rows.length}
              <span class="pick">
                <Select
                  value={previewValue}
                  options={[{ value: '', label: 'Default' }, ...rows.map((value) => ({ value, label: value }))]}
                  ariaLabel="Parameters to preview"
                  onChange={(value) => (previewValue = value)}
                />
              </span>
            {/if}
            <span class="pick">
              <Select
                value={load}
                options={[
                  { value: 'occupancy', label: 'Occupancy' },
                  { value: 'equipment', label: 'Equipment' },
                ]}
                ariaLabel="Schedule"
                onChange={(value) => (load = value as typeof load)}
              />
            </span>
          {/if}
        </div>
        {#if !spaceUses.length}
          <p class="hint">Add a SpaceUse in the Component Library to preview.</p>
        {:else if preview}
          <svg viewBox="-28 -4 {W + 48} {H + 22}" role="img" aria-label="Base {load} schedule and 20 sampled buildings, January weekday">
            <line x1="0" y1={H} x2={W} y2={H} class="axis" />
            {#each [0, 6, 12, 18, 23] as h}
              <text x={(h * W) / 23} y={H + 16} text-anchor="middle">{h}h</text>
            {/each}
            <text x="-6" y={H} text-anchor="end">0</text>
            <text x="-6" y="14" text-anchor="end">{+yMax.toFixed(2)}</text>
            {#each preview.samples as sample}<path d={path(sample.curves[load])} class="sample" />{/each}
            <path d={path(preview.base[load])} class="base" />
          </svg>
          <p class="hint">
            January weekday: library schedule (dark) and 20 sampled buildings.
            {#if shifts.length}Time shifts {Math.min(...shifts).toFixed(1)} to {Math.max(...shifts).toFixed(1)} h.{/if}
          </p>
        {/if}
      </div>
    {/if}
</section>

<style>
  .variability { display: flex; flex-direction: column; gap: var(--space-5); max-width: 960px; }
  .section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-4); }
  .intro { font-size: var(--text-md); }
  .saved-line { margin-top: var(--space-1); color: var(--text-faint); font-size: var(--text-xs); }
  .settings { --field-min: 180px; }
  .controls { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
  .pick { width: 200px; }
  td input { width: 90px; text-align: right; }
  svg { width: 100%; max-width: 640px; }
  svg text { font-size: var(--text-2xs); fill: var(--text-muted); }
  .axis { stroke: var(--border); }
  .sample { fill: none; stroke: var(--accent); stroke-opacity: 0.3; stroke-width: 1; }
  .base { fill: none; stroke: var(--text); stroke-width: 2; }
</style>
