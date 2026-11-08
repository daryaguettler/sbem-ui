<script lang="ts">
  /**
   * One uncertain number: its curve's shape and parameters, an optional cut, and the curve
   * drawn with the n variant values on it and the component's current value. The preview
   * comes from the server, which computes it the way the compile will.
   */
  import Select from '../Select.svelte';
  import Icon from '../Icon.svelte';
  import type { FieldPreview } from '../../api/componentPriors';
  import {
    SHAPES,
    defaultSpec,
    formatPairs,
    parseList,
    parsePairs,
    shapeInfo,
    type CurveSpec,
    type Shape,
  } from '../../utils/componentPriors';

  let {
    label,
    spec,
    preview,
    now,
    onChange,
    onRemove,
  }: {
    label: string;
    spec: CurveSpec;
    preview: FieldPreview | null;
    /** The component's current value of this number. */
    now: number | null;
    onChange: (spec: CurveSpec) => void;
    onRemove: () => void;
  } = $props();

  const W = 300;
  const H = 64;
  const info = $derived(shapeInfo(spec.shape));
  let cutOpen = $state(false);
  const hasCut = $derived(spec.lower != null || spec.upper != null);

  const fmt = (value: number) => String(Number(value.toPrecision(3)));

  const domain = $derived.by(() => {
    const xs = [...(preview?.x ?? []), ...(preview?.values ?? []), ...(now !== null ? [now] : [])];
    if (xs.length === 0) return null;
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    const pad = (hi - lo || Math.abs(lo) || 1) * 0.03;
    return [lo - pad, hi + pad] as const;
  });
  const sx = (x: number) => (domain ? ((x - domain[0]) / (domain[1] - domain[0])) * W : 0);
  const path = $derived.by(() => {
    if (!preview || !domain || preview.x.length === 0) return '';
    const top = Math.max(...preview.density) || 1;
    const points = preview.x.map((x, i) => `${sx(x).toFixed(1)},${(H - 4 - (preview.density[i] / top) * (H - 10)).toFixed(1)}`);
    return `M${sx(preview.x[0]).toFixed(1)},${H - 4} L${points.join(' L')} L${sx(preview.x[preview.x.length - 1]).toFixed(1)},${H - 4} Z`;
  });

  function setShape(shape: string) {
    // keep the centre: start the new shape around the current value
    onChange({ ...defaultSpec(shape as Shape, now), lower: spec.lower ?? null, upper: spec.upper ?? null });
  }

  function setParam(key: string, kind: string, text: string) {
    const value = kind === 'number' ? Number(text) : kind === 'list' ? parseList(text) : kind === 'pairs' ? parsePairs(text) : text;
    onChange({ ...spec, [key]: value });
  }

  function setCut(key: 'lower' | 'upper', text: string) {
    onChange({ ...spec, [key]: text.trim() === '' ? null : Number(text) });
  }

  function shown(key: string, kind: string): string {
    const value = spec[key];
    if (kind === 'list') return ((value as number[]) ?? []).join(', ');
    if (kind === 'pairs') return formatPairs(value);
    return value === undefined || value === null ? '' : String(value);
  }
</script>

<div class="distribution">
  <div class="head">
    <strong>{label}</strong>
    <div class="shape">
      <Select value={spec.shape} options={SHAPES.map((s) => ({ value: s.id, label: s.label }))} onChange={setShape} ariaLabel={`${label}: shape`} />
    </div>
    <button type="button" class="btn btn-ghost btn-sm" onclick={onRemove} aria-label={`Make ${label} certain again`} title="Make it certain again">
      <Icon name="x" size={14} />
    </button>
  </div>

  <div class="params">
    {#each info.params as param (param.key)}
      <label class:wide={param.kind !== 'number'}>
        <span>{param.label}</span>
        <input
          type={param.kind === 'number' ? 'number' : 'text'}
          step="any"
          value={shown(param.key, param.kind)}
          placeholder={param.kind === 'list' ? 'e.g. 0.4, 0.6, 0.8' : param.kind === 'pairs' ? 'e.g. a=2, scale=0.5' : ''}
          aria-label={`${label}: ${param.label}`}
          onchange={(event) => setParam(param.key, param.kind, (event.currentTarget as HTMLInputElement).value)}
        />
      </label>
    {/each}
  </div>

  {#if domain}
    <svg class="curve" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${label} curve`}>
      <path d={path} class="area" />
      {#each preview?.values ?? [] as value}
        <line x1={sx(value)} x2={sx(value)} y1={H - 4} y2={H - 16} class="variant" />
      {/each}
      {#if now !== null}
        <line x1={sx(now)} x2={sx(now)} y1="2" y2={H - 4} class="now" />
      {/if}
      <line x1="0" x2={W} y1={H - 4} y2={H - 4} class="axis" />
    </svg>
    <div class="scale">
      <span>{fmt(domain[0])}</span>
      {#if now !== null}<span class="now-label">now {fmt(now)}</span>{/if}
      <span>{fmt(domain[1])}</span>
    </div>
    {#if preview?.values.length}
      <p class="values" title="The value each variant takes">{preview.values.map(fmt).join(' · ')}</p>
    {/if}
  {/if}

  {#if cutOpen || hasCut}
    <div class="params cut">
      <label><span>Not below</span><input type="number" step="any" value={spec.lower ?? ''} aria-label={`${label}: not below`} onchange={(e) => setCut('lower', (e.currentTarget as HTMLInputElement).value)} /></label>
      <label><span>Not above</span><input type="number" step="any" value={spec.upper ?? ''} aria-label={`${label}: not above`} onchange={(e) => setCut('upper', (e.currentTarget as HTMLInputElement).value)} /></label>
    </div>
  {:else}
    <button type="button" class="btn btn-link" onclick={() => (cutOpen = true)}>Cut the curve at a limit</button>
  {/if}
</div>

<style>
  .distribution { display: flex; flex-direction: column; gap: var(--space-2); }
  .head { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); }
  .head strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .shape { flex: 1; min-width: 0; }
  .params { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .params label { display: flex; flex-direction: column; gap: 2px; font-size: var(--text-xs); color: var(--text-2); width: 88px; }
  .params label.wide { width: 100%; }
  .params input { width: 100%; }
  .curve { width: 100%; height: 64px; display: block; }
  .area { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
  .variant { stroke: var(--text); stroke-width: 2; vector-effect: non-scaling-stroke; }
  .now { stroke: var(--warn-text); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
  .axis { stroke: var(--border-strong); stroke-width: 1; vector-effect: non-scaling-stroke; }
  .scale { display: flex; justify-content: space-between; font-size: var(--text-xs); color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .now-label { color: var(--warn-text); }
  .values { margin: 0; font-size: var(--text-xs); color: var(--text-2); font-variant-numeric: tabular-nums; }
  .btn-link { align-self: flex-start; font-size: var(--text-xs); }
</style>
