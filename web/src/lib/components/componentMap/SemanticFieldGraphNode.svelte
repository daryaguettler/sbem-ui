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
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    padding: 10px 12px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    position: relative;
    overflow: hidden;
    color: #111827;
  }

  .color-bar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: var(--field-color, #2563eb);
  }

  .node.selected {
    border-color: #2563eb;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
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
    color: #6b7280;
  }
</style>
