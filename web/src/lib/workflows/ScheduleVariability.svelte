<script lang="ts">
  /**
   * Schedule variability (schedule-variability.yaml, globi's schedule_variability_config):
   * seeded per-building noise on the library's schedules, so buildings sharing a SpaceUse
   * don't all run identical profiles. Strengths can differ per value of one semantic field.
   * The preview runs globi's own perturbation on a SpaceUse for 20 synthetic buildings.
   */
  import { onMount } from 'svelte';
  import { fetchSavedArtifact, formatSavedAt, saveArtifact } from '../api/artifacts';
  import { fetchComponentRecords } from '../api/componentLibrary';
  import { markSaved, savedAt } from '../stores/projectArtifacts';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';

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

<section class="workflow">
  <div class="workflow-header">
    <div>
      <h1>Schedule Variability</h1>
      <p class="subtitle">Give each building its own seeded variation, so buildings sharing a schedule don't all switch on at once.</p>
      <p class="saved-line">{formatSavedAt($savedAt['schedule-variability'])}{dirty ? ' · unsaved changes' : ''}</p>
    </div>
    <button type="button" onclick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</button>
  </div>

  <div class="workflow-content">
    {#if error}<p class="error">{error}</p>{/if}
    {#if loading}
      <p class="muted">Loading…</p>
    {:else}
      <div class="panel">
        <div class="controls">
          <label>Seed <input type="number" min="0" step="1" bind:value={doc.seed} oninput={() => (dirty = true)} /></label>
          <label>
            Vary by
            <select value={doc.semantic_field ?? ''} onchange={(e) => setField(e.currentTarget.value)}>
              <option value="">— nothing —</option>
              {#each Object.keys(options) as name}<option value={name}>{name}</option>{/each}
            </select>
          </label>
        </div>
        <table>
          <thead>
            <tr><th></th>{#each COLUMNS as col}<th>{col.label}</th>{/each}</tr>
          </thead>
          <tbody>
            <tr>
              <td>Default</td>
              {#each COLUMNS as col}
                <td>
                  <input type="number" min="0" max={col.max} step={col.step} bind:value={doc.default[col.key]} oninput={() => (dirty = true)} />
                </td>
              {/each}
            </tr>
            {#each rows as value}
              <tr>
                <td>{value}</td>
                {#each COLUMNS as col}
                  <td>
                    <input
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
        {#if rows.length}<p class="muted">Empty cells use the default.</p>{/if}
      </div>

      <div class="panel">
        <div class="controls">
          <h2>Preview</h2>
          {#if spaceUses.length}
            <select bind:value={spaceUse} aria-label="SpaceUse">
              {#each spaceUses as name}<option value={name}>{name}</option>{/each}
            </select>
            {#if rows.length}
              <select bind:value={previewValue} aria-label="Parameters to preview">
                <option value="">Default</option>
                {#each rows as value}<option value={value}>{value}</option>{/each}
              </select>
            {/if}
            <select bind:value={load} aria-label="Schedule">
              <option value="occupancy">Occupancy</option>
              <option value="equipment">Equipment</option>
            </select>
          {/if}
        </div>
        {#if !spaceUses.length}
          <p class="muted">Add a SpaceUse in the Component Library to preview.</p>
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
          <p class="muted">
            January weekday: library schedule (dark) and 20 sampled buildings.
            {#if shifts.length}Time shifts {Math.min(...shifts).toFixed(1)} to {Math.max(...shifts).toFixed(1)} h.{/if}
          </p>
        {/if}
      </div>
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
  .workflow-content { padding: 32px; display: flex; flex-direction: column; gap: 20px; max-width: 960px; }
  .panel { border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .panel h2 { margin: 0; font-size: 15px; }
  .controls { display: flex; align-items: center; gap: 12px; font-size: 13px; flex-wrap: wrap; }
  table { border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-weight: 500; color: var(--text-muted); padding: 0 6px 6px 0; }
  td { padding: 2px 6px 2px 0; }
  input, select { border: 1px solid var(--border); border-radius: 6px; padding: 4px 6px; font-size: 13px; background: var(--surface); color: var(--text); }
  td input { width: 90px; }
  .controls input { width: 64px; }
  svg { width: 100%; max-width: 640px; }
  svg text { font-size: 11px; fill: var(--text-muted); }
  .axis { stroke: var(--border); }
  .sample { fill: none; stroke: var(--accent); stroke-opacity: 0.3; stroke-width: 1; }
  .base { fill: none; stroke: var(--text); stroke-width: 2; }
  button { border: none; border-radius: 8px; background: var(--accent); color: var(--on-accent); padding: 8px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .muted { color: var(--text-muted); font-size: 13px; margin: 0; }
  .error { color: var(--err-text); font-size: 13px; margin: 0; }
</style>
