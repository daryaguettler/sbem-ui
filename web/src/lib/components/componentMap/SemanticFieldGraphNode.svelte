<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte';

  type FieldNodeData = {
    fieldName: string;
    fieldType: string;
    optionCount: number;
    color: string;
  };

  let { data, selected = false }: { data: FieldNodeData; selected?: boolean } = $props();
</script>

<div class="node" class:selected style={`--field-color:${data.color}`}>
  <Handle type="source" position={Position.Bottom} id="bottom" />
  <div class="color-bar"></div>
  <div class="title">
    <span class="dot" style={`background:${data.color}`}></span>
    <span>{data.fieldName}</span>
  </div>
  <div class="meta">{data.optionCount} options</div>
</div>

<style>
  .node {
    min-width: 170px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    padding: var(--space-3);
    position: relative;
    overflow: hidden;
    color: var(--text);
  }

  .color-bar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: var(--field-color, var(--accent));
  }

  .node.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--focus-ring);
  }

  .title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
    font-weight: 600;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-sm);
  }

  .meta {
    margin-top: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
</style>
