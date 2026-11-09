<script lang="ts">
  /**
   * A 24-hour profile as bars you draw on: press and drag across hours to paint values.
   * Each bar is also a keyboard slider (arrow keys; Shift for 5 steps).
   * `overlays` are faint extra curves, e.g. sampled buildings' copies of this profile.
   */
  import { LIMITS, snap, type Limit } from '../../utils/schedules';

  let {
    values,
    limit,
    overlays = [],
    label,
    onChange,
  }: {
    values: number[];
    limit: Limit;
    overlays?: number[][];
    label: string;
    onChange: (values: number[]) => void;
  } = $props();

  const W = 480;
  const H = 170;
  const BAR = W / 24;

  // Fractions always span 0-1; other limits span their values plus some headroom.
  let domain = $derived.by(() => {
    if (limit === 'Fraction') return [0, 1] as const;
    const all = [...values, ...overlays.flat()];
    const [lo, hi] = limit === 'Temperature' ? [10, 30] : [0, 1];
    return [Math.floor(Math.min(lo, ...all) - 1), Math.ceil(Math.max(hi, ...all) + 1)] as const;
  });
  const y = (v: number) => H - ((v - domain[0]) / (domain[1] - domain[0])) * H;
  let ticks = $derived([domain[0], (domain[0] + domain[1]) / 2, domain[1]]);

  let svg: SVGSVGElement;
  let last: number | null = null;

  function point(event: PointerEvent): { hour: number; value: number } {
    const box = svg.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * (W + 40) - 32;
    const yy = ((event.clientY - box.top) / box.height) * (H + 26) - 6;
    const hour = Math.min(23, Math.max(0, Math.floor(x / BAR)));
    const value = domain[0] + ((H - yy) / H) * (domain[1] - domain[0]);
    return { hour, value: snap(Math.min(domain[1], Math.max(domain[0], value)), limit) };
  }

  function paint(event: PointerEvent) {
    const { hour, value } = point(event);
    const next = [...values];
    // fill every hour the pointer skipped over since the last event
    const from = last ?? hour;
    for (let h = Math.min(from, hour); h <= Math.max(from, hour); h++) next[h] = value;
    last = hour;
    onChange(next);
  }

  function onKey(hour: number, event: KeyboardEvent) {
    const step = LIMITS[limit].step * (event.shiftKey ? 5 : 1);
    const delta = { ArrowUp: step, ArrowRight: step, ArrowDown: -step, ArrowLeft: -step }[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    onChange(values.map((v, h) => (h === hour ? snap(v + delta, limit) : v)));
  }

  const line = (curve: number[]) => curve.map((v, h) => `${h ? 'L' : 'M'}${h * BAR + BAR / 2},${y(v)}`).join(' ');
</script>

<svg
  bind:this={svg}
  viewBox="-32 -6 {W + 40} {H + 26}"
  aria-label="{label}: drag across the hours to draw, or focus a bar and use the arrow keys"
  role="group"
  onpointerdown={(event) => {
    svg.setPointerCapture(event.pointerId);
    last = null;
    paint(event);
  }}
  onpointermove={(event) => {
    if (svg.hasPointerCapture(event.pointerId)) paint(event);
  }}
  onpointerup={() => (last = null)}
>
  {#each ticks as tick}
    <line x1="0" x2={W} y1={y(tick)} y2={y(tick)} class="grid" />
    <text x="-6" y={y(tick) + 3} text-anchor="end">{+tick.toFixed(2)}</text>
  {/each}
  {#each [0, 6, 12, 18] as h}
    <text x={h * BAR} y={H + 16} text-anchor="middle">{h}h</text>
  {/each}
  {#each values as value, h}
    <rect
      x={h * BAR + 1}
      width={BAR - 2}
      y={Math.min(y(value), y(Math.max(domain[0], 0)))}
      height={Math.max(1, Math.abs(y(Math.max(domain[0], 0)) - y(value)))}
      class="bar"
      role="slider"
      tabindex="0"
      aria-label="{label}, hour {h}"
      aria-valuenow={value}
      aria-valuemin={domain[0]}
      aria-valuemax={domain[1]}
      onkeydown={(event) => onKey(h, event)}
    ><title>{h}:00 · {value}</title></rect>
  {/each}
  {#each overlays as curve}<path d={line(curve)} class="overlay" />{/each}
</svg>

<style>
  svg { width: 100%; touch-action: none; cursor: crosshair; user-select: none; }
  text { font-size: var(--text-2xs); fill: var(--text-muted); }
  .grid { stroke: var(--border); }
  .bar { fill: var(--accent); fill-opacity: 0.75; }
  .bar:hover { fill-opacity: 1; }
  .bar:focus-visible { outline: none; fill-opacity: 1; stroke: var(--text); stroke-width: 1.5; }
  .overlay { fill: none; stroke: var(--text); stroke-opacity: 0.25; stroke-width: 1; pointer-events: none; }
</style>
