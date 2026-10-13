<script lang="ts">
  import {
    Background,
    Controls,
    MiniMap,
    SvelteFlow,
    ConnectionLineType,
    MarkerType,
    type Connection,
    type Edge,
    type Node,
    Position,
  } from '@xyflow/svelte';
  import SemanticFieldGraphNode from './SemanticFieldGraphNode.svelte';
  import ComponentGraphNode from './ComponentGraphNode.svelte';
  import { componentMapStore } from '../../stores/componentMapStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { resolvedTheme } from '../../stores/theme';
  import {
    buildComponentLevels,
    collectSelectors,
    countHiddenChildren,
    fieldColor,
    getSelectorAtPath,
    getSelectorStatus,
    isComponentVisible,
  } from '../../utils/componentMapTree';

  const nodeTypes = {
    semanticField: SemanticFieldGraphNode,
    componentLevel: ComponentGraphNode,
  };

  const defaultEdgeOptions = {
    type: 'smoothstep',
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 12,
      height: 12,
    },
  };

  const componentLevels = buildComponentLevels();
  const fieldColumnGap = 210;
  const componentColumnGap = 280;
  const componentRowGap = 150;

  function fieldNodeId(fieldId: string) {
    return `field_${fieldId}`;
  }

  function isFieldNode(nodeId: string) {
    return nodeId.startsWith('field_');
  }

  function isComponentNode(nodeId: string) {
    return nodeId.startsWith('component_');
  }

  function componentPathFromId(nodeId: string) {
    return componentLevels.find((level) => level.id === nodeId)?.path || null;
  }

  function buildFieldNodes(theme: 'light' | 'dark'): Node[] {
    return $semanticFieldsStore.fields.map((field, index) => ({
      id: fieldNodeId(field.id),
      type: 'semanticField',
      position: { x: 40 + index * fieldColumnGap, y: 20 },
      data: {
        fieldName: field.name,
        fieldType: field.type,
        optionCount: field.options.length,
        color: fieldColor(index, theme),
      },
      sourcePosition: Position.Bottom,
    }));
  }

  function buildComponentNodes(): Node[] {
    if (!$componentMapStore.map) return [];

    const expandedPaths = new Set($componentMapStore.expandedPaths);
    const visibleLevels = componentLevels.filter((level) =>
      isComponentVisible($componentMapStore.map!, level.path, expandedPaths)
    );
    const grouped: Record<number, number> = {};

    return visibleLevels.map((level) => {
      const depthIndex = grouped[level.depth] ?? 0;
      grouped[level.depth] = depthIndex + 1;
      const selector = getSelectorAtPath($componentMapStore.map!, level.path);
      const childCount = componentLevels.some((entry) => entry.path.startsWith(`${level.path}.`));

      return {
        id: level.id,
        type: 'componentLevel',
        position: {
          x: 40 + depthIndex * componentColumnGap,
          y: 180 + level.depth * componentRowGap,
        },
        data: {
          path: level.path,
          displayName: level.displayName,
          description: level.description,
          linkedFields: selector?.source_fields || [],
          status: getSelectorStatus($componentMapStore.map!, level.path),
          hiddenChildCount: countHiddenChildren(
            $componentMapStore.map!,
            level.path,
            componentLevels,
            expandedPaths
          ),
          canExpand: Boolean(selector && childCount),
          isExpanded: expandedPaths.has(level.path),
        },
        targetPosition: Position.Top,
      };
    });
  }

  function buildEdges(theme: 'light' | 'dark'): Edge[] {
    if (!$componentMapStore.map) return [];

    const expandedPaths = new Set($componentMapStore.expandedPaths);
    const visiblePaths = new Set(
      componentLevels
        .filter((level) => isComponentVisible($componentMapStore.map!, level.path, expandedPaths))
        .map((level) => level.path)
    );

    const fieldColorByName = Object.fromEntries(
      $semanticFieldsStore.fields.map((field, index) => [field.name, fieldColor(index, theme)])
    );
    const fieldIdByName = Object.fromEntries(
      $semanticFieldsStore.fields.map((field) => [field.name, fieldNodeId(field.id)])
    );
    const componentIdByPath = Object.fromEntries(
      componentLevels.map((level) => [level.path, level.id])
    );

    return collectSelectors($componentMapStore.map).flatMap((selector) => {
      if (!visiblePaths.has(selector.path)) return [];
      const targetId = componentIdByPath[selector.path];
      if (!targetId) return [];

      return selector.source_fields.map((fieldName) => {
        const sourceId = fieldIdByName[fieldName];
        if (!sourceId) return null;
        const color = fieldColorByName[fieldName] || fieldColor(-1, theme);
        return {
          id: `edge_${sourceId}_${targetId}`,
          source: sourceId,
          sourceHandle: 'bottom',
          target: targetId,
          targetHandle: 'top',
          type: 'smoothstep',
          style: `stroke:${color}; stroke-width:2px;`,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 12,
            height: 12,
            color,
          },
        };
      }).filter(Boolean) as Edge[];
    });
  }

  // The theme is passed in so a light/dark switch re-runs these (field colors are hex).
  $: nodes = [...buildFieldNodes($resolvedTheme), ...buildComponentNodes()];
  $: edges = buildEdges($resolvedTheme);

  function handleConnect(connection: Connection) {
    if (!connection.source || !connection.target || !$componentMapStore.map) return;

    const sourceIsField = isFieldNode(connection.source);
    const targetIsComponent = isComponentNode(connection.target);
    if (!sourceIsField || !targetIsComponent) return;

    const componentPath = componentPathFromId(connection.target);
    const field = $semanticFieldsStore.fields.find(
      (entry) => fieldNodeId(entry.id) === connection.source
    );
    if (!componentPath || !field) return;

    componentMapStore.linkField(componentPath, field.name);
    componentMapStore.setSelectedPath(componentPath);
  }

  function handleDelete({ edges: deletedEdges }: { edges: Edge[]; nodes: Node[] }) {
    if (!$componentMapStore.map) return;

    for (const edge of deletedEdges) {
      const componentPath = componentPathFromId(edge.target);
      const field = $semanticFieldsStore.fields.find(
        (entry) => fieldNodeId(entry.id) === edge.source
      );
      if (!componentPath || !field) continue;
      componentMapStore.unlinkField(componentPath, field.name);
    }
  }

  function handleNodeClick({ node }: { node: Node }) {
    if (node.type === 'componentLevel') {
      const path = componentPathFromId(node.id);
      if (path) componentMapStore.setSelectedPath(path);
    }
  }

  function isValidConnection(connection: Connection | Edge) {
    if (!connection.source || !connection.target) return false;
    return isFieldNode(connection.source) && isComponentNode(connection.target);
  }
</script>

<div class="canvas">
  <SvelteFlow
    {nodes}
    {edges}
    {nodeTypes}
    {defaultEdgeOptions}
    colorMode={$resolvedTheme}
    connectionLineType={ConnectionLineType.SmoothStep}
    {isValidConnection}
    fitView
    deleteKey={['Backspace', 'Delete']}
    onconnect={handleConnect}
    ondelete={handleDelete}
    onnodeclick={handleNodeClick}
  >
    <Background gap={24} />
    <Controls position="bottom-right" />
    <MiniMap position="bottom-left" />
  </SvelteFlow>
</div>
<ul class="legend" aria-label="Component status">
  <li><span class="swatch mapped"></span>✓ Mapped: has its own selector</li>
  <li><span class="swatch inherited"></span>↳ Inherited: uses a parent's selector</li>
  <li><span class="swatch unmapped"></span>✕ Unmapped: no selector yet</li>
</ul>

<style>
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    margin-top: 8px;
    list-style: none;
    font-size: 12px;
    color: var(--text-muted);
  }

  .legend li {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .swatch {
    width: 18px;
    height: 12px;
    border-radius: 3px;
    border: 2px solid;
  }

  .swatch.mapped {
    border-color: var(--ok);
  }

  .swatch.inherited {
    border-color: var(--accent);
    border-style: dashed;
  }

  .swatch.unmapped {
    border-color: var(--err);
    border-style: dotted;
    border-width: 3px;
  }

  .canvas {
    height: 560px;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    background: var(--surface);
  }

  :global(.svelte-flow__controls button) {
    background: var(--surface);
    color: var(--text-2);
    border: 1px solid var(--border);
  }

  /* xyflow's own dark theme comes from colorMode; these keep it on our surfaces. */
  .canvas :global(.svelte-flow) {
    --xy-background-color: var(--surface);
    --xy-node-background-color: var(--surface);
    --xy-minimap-background-color: var(--surface-2);
    --xy-controls-button-background-color: var(--surface);
    --xy-controls-button-background-color-hover: var(--surface-3);
    --xy-controls-button-color: var(--text-2);
    --xy-controls-button-border-color: var(--border);
    --xy-edge-stroke: var(--text-faint);
  }

  :global(.svelte-flow__minimap) {
    border: 1px solid var(--border);
    border-radius: 8px;
  }
</style>
