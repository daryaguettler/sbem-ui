<script lang="ts">
  /**
   * The prior tree itself: what is sampled from what, left to right.
   *
   * Columns are sampling depth, so an edge always points forward and the picture
   * doubles as the execution order. Node kind is carried by shape and a written
   * label as well as color -- context fields come from the GIS data, compound
   * nodes are the generated join keys, and the rest are sampled features.
   */
  import type { DependencyGraph } from '../../types/priorTrees';

  export let graph: DependencyGraph;

  const COLUMN_WIDTH = 210;
  const ROW_HEIGHT = 62;
  const NODE_WIDTH = 168;
  const NODE_HEIGHT = 38;
  const PADDING = 16;

  // Colors are CSS variables (set via style, since SVG presentation attributes can't
  // resolve var()), tinted toward the surface so they follow light/dark mode.
  const tint = (hue: string) => `color-mix(in srgb, ${hue} 16%, var(--surface))`;
  const KIND_STYLES: Record<string, { fill: string; stroke: string; dash: string; label: string }> = {
    context: { fill: 'var(--surface-3)', stroke: 'var(--text-faint)', dash: 'none', label: 'From GIS' },
    compound: { fill: tint('var(--series-7)'), stroke: 'var(--series-7)', dash: '4 3', label: 'Join key' },
    conditional: { fill: tint('var(--series-1)'), stroke: 'var(--series-1)', dash: 'none', label: 'Conditioned' },
    unconditional: { fill: tint('var(--series-3)'), stroke: 'var(--series-3)', dash: 'none', label: 'Unconditioned' },
  };

  interface Placed {
    name: string;
    kind: string;
    x: number;
    y: number;
  }

  /** Lay each node out in its depth column, stacked in the order the backend sorted them. */
  $: placed = (() => {
    const perColumn = new Map<number, number>();
    return graph.nodes.map((node) => {
      const row = perColumn.get(node.depth) ?? 0;
      perColumn.set(node.depth, row + 1);
      return {
        name: node.name,
        kind: node.kind,
        x: PADDING + node.depth * COLUMN_WIDTH,
        y: PADDING + row * ROW_HEIGHT,
      } as Placed;
    });
  })();

  $: positions = new Map(placed.map((node) => [node.name, node]));
  $: width = Math.max(...placed.map((node) => node.x + NODE_WIDTH), 320) + PADDING;
  $: height = Math.max(...placed.map((node) => node.y + NODE_HEIGHT), 80) + PADDING;

  /** A cubic curve from the right edge of the source to the left edge of the target. */
  function edgePath(from: string, to: string): string | null {
    const source = positions.get(from);
    const target = positions.get(to);
    if (!source || !target) return null;
    const x1 = source.x + NODE_WIDTH;
    const y1 = source.y + NODE_HEIGHT / 2;
    const x2 = target.x;
    const y2 = target.y + NODE_HEIGHT / 2;
    const midpoint = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${midpoint} ${y1}, ${midpoint} ${y2}, ${x2} ${y2}`;
  }

  /** Long compound names ("compound.Typology.Age_bracket") need trimming to fit the node. */
  function displayName(name: string): string {
    const trimmed = name.startsWith('compound.') ? name.slice('compound.'.length) : name;
    return trimmed.length > 22 ? `${trimmed.slice(0, 21)}…` : trimmed;
  }
</script>

{#if graph.nodes.length === 0}
  <p class="empty">Validate the prior tree to see how its features depend on each other.</p>
{:else}
  <div class="graph">
    <svg viewBox="0 0 {width} {height}" width={width} height={height} role="img" aria-label="Prior sampling dependency graph">
      <defs>
        <marker id="prior-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 0 L 8 4 L 0 8 z" style="fill: var(--text-faint)" />
        </marker>
      </defs>

      {#each graph.edges as edge}
        {@const path = edgePath(edge.from, edge.to)}
        {#if path}
          <path d={path} fill="none" style="stroke: var(--text-faint)" stroke-width="2" marker-end="url(#prior-arrow)" />
        {/if}
      {/each}

      {#each placed as node}
        {@const style = KIND_STYLES[node.kind] ?? KIND_STYLES.context}
        <g>
          <rect
            x={node.x}
            y={node.y}
            width={NODE_WIDTH}
            height={NODE_HEIGHT}
            rx={node.kind === 'compound' ? 16 : 6}
            style="fill: {style.fill}; stroke: {style.stroke}; stroke-dasharray: {style.dash};"
            stroke-width="1.5"
          />
          <text x={node.x + 10} y={node.y + 16} font-size="12" font-weight="600" style="fill: var(--text)">
            {displayName(node.name)}
            <title>{node.name}</title>
          </text>
          <text x={node.x + 10} y={node.y + 29} font-size="10" style="fill: var(--text-muted)">
            {style.label}
          </text>
        </g>
      {/each}
    </svg>
  </div>

  <ul class="legend">
    {#each Object.values(KIND_STYLES) as style}
      <li>
        <span class="swatch" style="background: {style.fill}; border-color: {style.stroke}; border-style: {style.dash === 'none' ? 'solid' : 'dashed'};"></span>
        {style.label}
      </li>
    {/each}
    <li class="note">Arrows point from a feature to whatever is sampled from it.</li>
  </ul>
{/if}

<style>
  .graph {
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    padding: 4px;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 16px;
    margin: 10px 0 0;
    padding: 0;
    list-style: none;
    font-size: 12px;
    color: var(--text-2);
  }

  .legend li {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .swatch {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    border: 1.5px solid;
  }

  .note {
    color: var(--text-faint);
  }

  .empty {
    margin: 0;
    font-size: 13px;
    color: var(--text-muted);
  }
</style>
