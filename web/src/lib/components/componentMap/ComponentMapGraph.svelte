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
      color: '#94a3b8',
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

  function buildFieldNodes(): Node[] {
    return $semanticFieldsStore.fields.map((field, index) => ({
      id: fieldNodeId(field.id),
      type: 'semanticField',
      position: { x: 40 + index * fieldColumnGap, y: 20 },
      data: {
        fieldName: field.name,
        fieldType: field.type,
        optionCount: field.options.length,
        color: fieldColor(field.name, index),
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
          color: level.color,
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

  function buildEdges(): Edge[] {
    if (!$componentMapStore.map) return [];

    const expandedPaths = new Set($componentMapStore.expandedPaths);
    const visiblePaths = new Set(
      componentLevels
        .filter((level) => isComponentVisible($componentMapStore.map!, level.path, expandedPaths))
        .map((level) => level.path)
    );

    const fieldColorByName = Object.fromEntries(
      $semanticFieldsStore.fields.map((field, index) => [field.name, fieldColor(field.name, index)])
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
        const color = fieldColorByName[fieldName] || '#94a3b8';
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

  $: nodes = [...buildFieldNodes(), ...buildComponentNodes()];
  $: edges = buildEdges();

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

<style>
  .canvas {
    height: 560px;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
    background: #ffffff;
  }

  :global(.svelte-flow__controls button) {
    background: #ffffff;
    color: #374151;
    border: 1px solid #e5e7eb;
  }

  :global(.svelte-flow__minimap) {
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }
</style>
