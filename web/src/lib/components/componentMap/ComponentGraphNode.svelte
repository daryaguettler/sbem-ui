<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte';
  import { componentMapStore } from '../../stores/componentMapStore';

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
    mapped: { color: 'var(--ok)', icon: '✓', label: 'Mapped' },
    inherited: { color: 'var(--accent)', icon: '↳', label: 'Inherited' },
    unmapped: { color: 'var(--err)', icon: '✕', label: 'Unmapped' },
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
        <button type="button" class="icon-btn" onclick={handleToggleExpand}>
          {data.isExpanded ? '−' : '+'}
        </button>
      {/if}
      <button type="button" class="icon-btn" onclick={(event) => { event.stopPropagation(); handleConfigure(); }}>
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
  <div class="status-badge"><span aria-hidden="true">{status.icon}</span> {status.label}</div>
</div>

<style>
  .node {
    min-width: 230px;
    border: 2px solid var(--status-color);
    border-radius: 8px;
    background: var(--surface);
    padding: 10px 12px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
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
    margin: -10px -12px 8px;
    background: var(--status-color);
    border-radius: 6px 6px 0 0;
  }

  .node.selected {
    box-shadow: 0 0 0 3px var(--focus-ring);
  }

  .header {
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }

  .title {
    font-size: 13px;
    font-weight: 600;
  }

  .path {
    font-size: 10px;
    color: var(--text-faint);
    font-family: monospace;
  }

  .actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-2);
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    cursor: pointer;
  }

  .description {
    margin-top: 6px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .stats {
    display: flex;
    gap: 10px;
    margin-top: 8px;
    font-size: 10px;
    color: var(--text-muted);
  }

  .status-badge {
    margin-top: 8px;
    display: inline-block;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--status-color) 14%, var(--surface));
    color: var(--text);
    font-weight: 600;
  }
</style>
