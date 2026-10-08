<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte';
  import { componentMapStore } from '../../stores/componentMapStore';

  type ComponentNodeData = {
    path: string;
    displayName: string;
    description: string;
    linkedFields: string[];
    color: string;
    status: 'unmapped' | 'mapped' | 'inherited';
    hiddenChildCount?: number;
    canExpand?: boolean;
    isExpanded?: boolean;
  };

  let { data, selected = false }: { data: ComponentNodeData; selected?: boolean } = $props();

  const statusColor = $derived(
    data.status === 'mapped' ? '#16a34a' : data.status === 'inherited' ? '#f97316' : '#ef4444'
  );
  const statusLabel = $derived(
    data.status === 'mapped' ? 'Mapped' : data.status === 'inherited' ? 'Inherited' : 'Unmapped'
  );

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
  style={`--node-color:${data.color}; --status-color:${statusColor}`}
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
  <div class="status-badge">{statusLabel}</div>
</div>

<style>
  .node {
    min-width: 230px;
    border: 2px solid var(--status-color);
    border-radius: 8px;
    background: #ffffff;
    padding: 10px 12px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    color: #111827;
    cursor: pointer;
  }

  .status-bar {
    height: 4px;
    margin: -10px -12px 8px;
    background: var(--status-color);
    border-radius: 6px 6px 0 0;
  }

  .node.selected {
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2);
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
    color: #9ca3af;
    font-family: monospace;
  }

  .actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    border: 1px solid #e5e7eb;
    background: #ffffff;
    color: #374151;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    cursor: pointer;
  }

  .description {
    margin-top: 6px;
    font-size: 11px;
    color: #6b7280;
  }

  .stats {
    display: flex;
    gap: 10px;
    margin-top: 8px;
    font-size: 10px;
    color: #6b7280;
  }

  .status-badge {
    margin-top: 8px;
    display: inline-block;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--status-color) 15%, white);
    color: var(--status-color);
    font-weight: 600;
  }
</style>
