<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte';
  import { componentMapStore } from '../../stores/componentMapStore';
  import Icon from '../Icon.svelte';

  type ComponentNodeData = {
    path: string;
    displayName: string;
    description: string;
    linkedFields: string[];
    status: 'unmapped' | 'mapped' | 'inherited';
    hiddenChildCount?: number;
    canExpand?: boolean;
    isExpanded?: boolean;
  };

  let { data, selected = false }: { data: ComponentNodeData; selected?: boolean } = $props();

  // Status is carried by border style and an icon as well as hue, so it survives
  // colorblindness and zoomed-out views: solid = mapped, dashed = inherited, dotted = unmapped.
  const STATUS = {
    mapped: { color: 'var(--ok)', icon: 'check', label: 'Mapped' },
    inherited: { color: 'var(--accent)', icon: 'corner-down-right', label: 'Inherited' },
    unmapped: { color: 'var(--err)', icon: 'x', label: 'Unmapped' },
  } as const;
  const status = $derived(STATUS[data.status]);

  function handleConfigure() {
    componentMapStore.setSelectedPath(data.path);
  }

  function handleToggleExpand(event: MouseEvent) {
    event.stopPropagation();
    componentMapStore.toggleExpandedPath(data.path);
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="node"
  class:selected
  data-status={data.status}
  style={`--status-color:${status.color}`}
  ondblclick={handleConfigure}
  role="button"
  tabindex="0"
  onkeydown={(event) => event.key === 'Enter' && handleConfigure()}
>
  <Handle type="target" position={Position.Top} id="top" />
  <div class="status-bar"></div>
  <div class="header">
    <div>
      <div class="title">{data.displayName}</div>
      <div class="path">{data.path}</div>
    </div>
    <div class="actions">
      {#if data.canExpand}
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          aria-label={data.isExpanded ? 'Collapse children' : 'Expand children'}
          onclick={handleToggleExpand}
        >
          <Icon name={data.isExpanded ? 'minus' : 'plus'} size={12} />
        </button>
      {/if}
      <button type="button" class="btn btn-secondary btn-sm" onclick={(event) => { event.stopPropagation(); handleConfigure(); }}>
        edit
      </button>
    </div>
  </div>
  <div class="description">{data.description}</div>
  <div class="stats">
    <span>{data.linkedFields.length} linked field{data.linkedFields.length === 1 ? '' : 's'}</span>
    {#if data.hiddenChildCount}
      <span>{data.hiddenChildCount} hidden</span>
    {/if}
  </div>
  <div class="tag status-badge"><Icon name={status.icon} size={12} />{status.label}</div>
</div>

<style>
  .node {
    min-width: 230px;
    border: 2px solid var(--status-color);
    border-radius: var(--radius);
    background: var(--surface);
    padding: var(--space-3);
    color: var(--text);
    cursor: pointer;
  }

  .node[data-status='inherited'] {
    border-style: dashed;
  }

  .node[data-status='unmapped'] {
    border-style: dotted;
    border-width: 3px;
  }

  .status-bar {
    height: 4px;
    margin: calc(-1 * var(--space-3)) calc(-1 * var(--space-3)) var(--space-2);
    background: var(--status-color);
    border-radius: var(--radius) var(--radius) 0 0;
  }

  .node.selected {
    box-shadow: 0 0 0 3px var(--focus-ring);
  }

  .header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-2);
  }

  .title {
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .path {
    font-size: var(--text-xs);
    color: var(--text-faint);
    font-family: var(--font-mono);
  }

  .actions {
    flex-wrap: nowrap;
    align-items: flex-start;
    gap: var(--space-1);
  }

  .description {
    margin-top: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .stats {
    display: flex;
    gap: var(--space-3);
    margin-top: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .status-badge {
    margin-top: var(--space-2);
    background: color-mix(in srgb, var(--status-color) 14%, var(--surface));
    color: var(--text);
  }
</style>
