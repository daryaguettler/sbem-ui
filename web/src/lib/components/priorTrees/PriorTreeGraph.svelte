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

  const KIND_STYLES: Record<string, { fill: string; stroke: string; ink: string; label: string }> = {
    context: { fill: '#f3f4f6', stroke: '#9ca3af', ink: '#374151', label: 'From GIS' },
    compound: { fill: '#ede9fe', stroke: '#7c3aed', ink: '#5b21b6', label: 'Join key' },
    conditional: { fill: '#dbeafe', stroke: '#2563eb', ink: '#1e40af', label: 'Conditioned' },
    unconditional: { fill: '#dcfce7', stroke: '#16a34a', ink: '#166534', label: 'Unconditioned' },
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
          <path d="M 0 0 L 8 4 L 0 8 z" fill="#9ca3af" />
        </marker>
      </defs>

      {#each graph.edges as edge}
        {@const path = edgePath(edge.from, edge.to)}
        {#if path}
          <path d={path} fill="none" stroke="#9ca3af" stroke-width="2" marker-end="url(#prior-arrow)" />
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
            fill={style.fill}
            stroke={style.stroke}
            stroke-width="1.5"
          />
          <text x={node.x + 10} y={node.y + 16} font-size="12" font-weight="600" fill={style.ink}>
            {displayName(node.name)}
            <title>{node.name}</title>
          </text>
          <text x={node.x + 10} y={node.y + 29} font-size="10" fill={style.ink} opacity="0.75">
            {style.label}
          </text>
        </g>
      {/each}
    </svg>
  </div>

  <ul class="legend">
    {#each Object.values(KIND_STYLES) as style}
      <li>
        <span class="swatch" style="background: {style.fill}; border-color: {style.stroke};"></span>
        {style.label}
      </li>
    {/each}
    <li class="note">Arrows point from a feature to whatever is sampled from it.</li>
  </ul>
{/if}

<style>
  .graph {
    overflow: auto;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
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
    color: #4b5563;
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
    color: #9ca3af;
  }

  .empty {
    margin: 0;
    font-size: 13px;
    color: #6b7280;
  }
</style>
