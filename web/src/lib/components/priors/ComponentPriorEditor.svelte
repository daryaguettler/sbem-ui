<script lang="ts">
  /**
   * A component's uncertainty: which of its numbers are uncertain, each with a curve, how
   * many variants it stands for (n), and how several numbers move together. Certain until
   * someone asks; edits go to componentPriorsStore, and saving compiles them into variants.
   * Used under a Component Map row and in the Component Library's record panel.
   */
  import { onMount } from 'svelte';
  import DistributionEditor from './DistributionEditor.svelte';
  import Explain from '../Explain.svelte';
  import Icon from '../Icon.svelte';
  import Select from '../Select.svelte';
  import { fetchComponentRecord, fetchComponentRecords, fetchComponentSchema, type ComponentRecord } from '../../api/componentLibrary';
  import { previewPrior, type PriorPreview } from '../../api/componentPriors';
  import { componentPriorsStore } from '../../stores/componentPriorsStore';
  import { dirtyKinds, saveDirtyArtifacts } from '../../stores/projectArtifacts';
  import { partRulesStore } from '../../stores/partRulesStore';
  import { DEFAULT_N, U, defaultSpec, insulated, keyField, priorFor, uninsulatedSpec, type ComponentPrior, type Link } from '../../utils/componentPriors';
  import { uValue } from '../../utils/optionValues';
  import { HELP } from '../../help';
  const help = HELP.componentPriors;

  let {
    type,
    name,
    record = null,
    conductivity = {},
    standalone = false,
    note = '',
  }: {
    type: string;
    name: string;
    /** The component's record, when the caller already has it. */
    record?: ComponentRecord | null;
    conductivity?: Record<string, number>;
    /** Show its own Save (the Component Library); on Component Map the page's Save covers it. */
    standalone?: boolean;
    note?: string;
  } = $props();

  let numbers = $state<string[]>([]);
  let loaded = $state<ComponentRecord | null>(null);
  let materials = $state<Record<string, number>>({});
  let preview = $state<PriorPreview | null>(null);
  let previewError = $state<string | null>(null);
  let saving = $state(false);
  let saveError = $state<string | null>(null);

  const prior = $derived(priorFor($componentPriorsStore, type, name));
  const current = $derived(record ?? loaded);
  const k = $derived(Object.keys(conductivity).length ? conductivity : materials);
  const available = $derived(numbers.filter((field) => !prior || !(field in prior.fields)));
  const link = $derived<Link>(prior?.link ?? 'independent');

  onMount(async () => {
    const needsMaterials = type === 'ConstructionAssembly' && Object.keys(conductivity).length === 0;
    const [schema, own, all] = await Promise.all([
      fetchComponentSchema(type).catch(() => null),
      record ? Promise.resolve(null) : fetchComponentRecord(type, name).catch(() => null),
      needsMaterials ? fetchComponentRecords('ConstructionMaterial').catch(() => []) : Promise.resolve([]),
    ]);
    loaded = own;
    materials = Object.fromEntries(all.map((m) => [m.Name, Number(m.Conductivity)]));
    // the numbers last: a curve starts around the component's value, so wait until it's known
    const first = keyField(type);
    const fields = (schema?.fields ?? []).filter((field) => field.kind === 'number').map((field) => field.name);
    numbers = [...(type === 'ConstructionAssembly' ? [U] : []), ...fields].sort((a, b) => Number(b === first) - Number(a === first));
  });

  function valueOf(field: string): number | null {
    if (!current) return null;
    if (field === U) return uValue((current.Layers as Array<Record<string, unknown>>) ?? [], k);
    const value = Number(current[field]);
    return Number.isFinite(value) ? value : null;
  }

  function set(next: ComponentPrior | null) {
    componentPriorsStore.setPrior(type, name, next);
  }

  function addNumber(field: string) {
    const base = prior ?? { n: DEFAULT_N, fields: {} };
    const value = valueOf(field);
    const layers = (current?.Layers as Array<Record<string, unknown>>) ?? [];
    const spec =
      field === U && value !== null && !insulated(layers, k)
        ? uninsulatedSpec(value) // its U can only go down: insulation can be added, not removed
        : defaultSpec('triangular', value);
    set({ ...base, fields: { ...base.fields, [field]: spec } });
  }

  function removeNumber(field: string) {
    if (!prior) return;
    const { [field]: _, ...rest } = prior.fields;
    set({ ...prior, fields: rest });
  }

  // redraw the curves a moment after the last edit
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const snapshot = prior ? JSON.stringify(prior) : null;
    clearTimeout(timer);
    if (!snapshot) {
      preview = null;
      return;
    }
    timer = setTimeout(async () => {
      try {
        preview = await previewPrior(type, name, JSON.parse(snapshot));
        previewError = null;
      } catch (e) {
        previewError = e instanceof Error ? e.message : 'Could not draw the curve.';
      }
    }, 250);
    return () => clearTimeout(timer);
  });

  async function save() {
    saving = true;
    saveError = null;
    try {
      await saveDirtyArtifacts(['component-priors']);
      const compile = $partRulesStore.compile;
      if (compile && !compile.ok) saveError = compile.errors.join(' ');
    } catch (e) {
      saveError = e instanceof Error ? e.message : 'Save failed.';
    } finally {
      saving = false;
    }
  }

  const labelOf = (field: string) => (field === U ? 'U-value (W/m²K)' : field);
</script>

<div class="prior">
  {#if !prior}
    <div class="certain">
      <span class="hint">Certain: every building with this component gets the same value.</span>
      {#if numbers.length}
        <button type="button" class="btn btn-secondary btn-sm" disabled={valueOf(numbers[0]) === null} onclick={() => addNumber(numbers[0])}>
          <Icon name="bell-curve" size={14} />Make {labelOf(numbers[0])} uncertain
        </button>
      {/if}
    </div>
    <Explain text={help.intro} />
  {:else}
    <Explain text={help.intro} />
    {#each Object.entries(prior.fields) as [field, spec] (field)}
      <DistributionEditor
        label={labelOf(field)}
        {spec}
        preview={preview?.fields[field] ?? null}
        now={valueOf(field)}
        onChange={(next) => set({ ...prior, fields: { ...prior.fields, [field]: next } })}
        onRemove={() => removeNumber(field)}
      />
    {/each}

    <div class="settings">
      <label class="n">
        <span>Variants (n) <Explain text={help.n} tip /></span>
        <input type="number" min="1" max="50" step="1" value={prior.n} aria-label="Variants (n)"
          onchange={(e) => set({ ...prior, n: Math.max(1, Math.min(50, Math.round(Number((e.currentTarget as HTMLInputElement).value) || 1))) })} />
      </label>
      {#if available.length}
        <div class="add">
          <Select value="" placeholder="Another number…" options={available.map((field) => ({ value: field, label: labelOf(field) }))} onChange={addNumber} ariaLabel="Make another number uncertain" />
        </div>
      {/if}
    </div>

    {#if Object.keys(prior.fields).length > 1}
      <div class="link">
        <span class="hint">These numbers <Explain text={help.link} tip /></span>
        <div class="toggle" role="radiogroup" aria-label="How the numbers move together">
          <button type="button" role="radio" aria-checked={link === 'independent'} class:selected={link === 'independent'} onclick={() => set({ ...prior, link: 'independent' })}>vary independently</button>
          <button type="button" role="radio" aria-checked={link === 'together'} class:selected={link === 'together'} onclick={() => set({ ...prior, link: 'together' })}>move together</button>
          <button type="button" role="radio" aria-checked={typeof link === 'number'} class:selected={typeof link === 'number'} onclick={() => set({ ...prior, link: 0.5 })}>are correlated</button>
        </div>
        {#if typeof link === 'number'}
          <label class="rho">ρ <input type="number" min="-0.95" max="0.95" step="0.05" value={link} aria-label="Correlation"
            onchange={(e) => set({ ...prior, link: Math.max(-0.95, Math.min(0.95, Number((e.currentTarget as HTMLInputElement).value) || 0)) })} /></label>
        {/if}
      </div>
    {/if}

    {#if preview?.errors.length}
      <ul class="errors" role="alert">{#each preview.errors as message}<li>{message}</li>{/each}</ul>
    {:else if previewError}
      <p class="error" role="alert">{previewError}</p>
    {:else if preview}
      <p class="hint">{prior.n} variants, each for 1 in {prior.n} buildings.{note ? ` ${note}` : ''}</p>
    {/if}
  {/if}

  {#if standalone && (prior || $dirtyKinds.includes('component-priors'))}
    <div class="actions">
      <button type="button" class="btn btn-sm" onclick={save} disabled={saving || !$dirtyKinds.includes('component-priors')}>{saving ? 'Saving…' : 'Save uncertainty'}</button>
      {#if saveError}<span class="error">{saveError}</span>{/if}
    </div>
  {/if}
</div>

<style>
  .prior { display: flex; flex-direction: column; gap: var(--space-3); }
  .certain { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  .settings { display: flex; align-items: flex-end; gap: var(--space-3); flex-wrap: wrap; }
  .n { display: flex; flex-direction: column; gap: 2px; font-size: var(--text-xs); color: var(--text-2); }
  .n input { width: 80px; }
  .add { flex: 1; min-width: 160px; }
  .link { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; font-size: var(--text-sm); }
  .toggle { display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); overflow: hidden; }
  .toggle button { min-height: var(--control-h-sm); padding: 0 var(--space-2); border: none; background: var(--surface); color: var(--text-2); font-size: var(--text-xs); cursor: pointer; }
  .toggle button + button { border-left: 1px solid var(--border-strong); }
  .toggle button.selected { background: var(--accent-soft); color: var(--text); font-weight: 600; }
  .rho { display: inline-flex; align-items: center; gap: 4px; }
  .rho input { width: 70px; }
  .errors { margin: 0; padding-left: 18px; font-size: var(--text-sm); color: var(--err-text); }
  .actions { display: flex; align-items: center; gap: var(--space-2); }
</style>
