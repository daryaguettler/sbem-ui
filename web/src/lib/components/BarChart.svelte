<script lang="ts">
  /** Horizontal bar chart (d3 scales, Svelte-rendered SVG): one bar per [label, value] row. */
  import { scaleBand, scaleLinear } from 'd3-scale';
  import { BATLOW_S } from '../charts/palette';

  export let rows: [string, number][] = [];
  export let unit = '';
  export let decimals = 1;

  const labelW = 110;
  const valueW = 56;
  const barH = 22;
  const gap = 6;

  let width = 0;
  $: height = rows.length * (barH + gap);
  $: y = scaleBand<string>().domain(rows.map(([n]) => n)).range([0, height]).paddingInner(gap / (barH + gap));
  $: x = scaleLinear().domain([0, Math.max(...rows.map(([, v]) => v), 1e-9)]).range([0, Math.max(width - labelW - valueW, 0)]);
</script>

<div class="chart" bind:clientWidth={width}>
  <svg {width} {height} role="img" aria-label="Bar chart{unit ? ` in ${unit}` : ''}">
    {#each rows as [name, value], i (name)}
      <text class="label" x={labelW - 8} y={(y(name) ?? 0) + barH / 2} text-anchor="end" dominant-baseline="middle">{name}</text>
      <rect x={labelW} y={y(name)} width={x(value)} height={y.bandwidth()} rx="2" fill={BATLOW_S[i % BATLOW_S.length]} />
      <text class="value" x={labelW + x(value) + 6} y={(y(name) ?? 0) + barH / 2} dominant-baseline="middle">{value.toFixed(decimals)}</text>
    {/each}
  </svg>
</div>

<style>
  .chart { width: 100%; }
  svg { display: block; }
  text { font-size: var(--text-sm); fill: var(--text-muted); }
  .value { fill: var(--text); font-variant-numeric: tabular-nums; }
</style>
