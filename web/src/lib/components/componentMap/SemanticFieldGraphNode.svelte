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
    border-radius: 8px;
    background: var(--surface);
    padding: 10px 12px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
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
    gap: 8px;
    font-size: 12px;
    font-weight: 600;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
  }

  .meta {
    margin-top: 6px;
    font-size: 11px;
    color: var(--text-muted);
  }
</style>
