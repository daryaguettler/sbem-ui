<script lang="ts">
  import type { WorkflowId } from '../types/workflow';
  import { workspaceStore } from '../stores/workspaceStore';

  export let currentWorkflow: WorkflowId;
  export let setWorkflow: (workflow: WorkflowId) => void;

  const workflows: Array<{ id: WorkflowId; label: string }> = [
    { id: 'gis-cleaning', label: 'GIS Cleaning' },
    { id: 'semantic-fields', label: 'Semantic Fields' },
    { id: 'component-library', label: 'Component Library' },
    { id: 'component-map', label: 'Component Map' },
    { id: 'prior-trees', label: 'Prior Trees' },
    { id: 'retrofits', label: 'Retrofits' },
    { id: 'sampling', label: 'Sampling' },
    { id: 'model-execution', label: 'Model Execution' },
    { id: 'project-files', label: 'Project Files' },
  ];
</script>

<aside class="sidebar">
  <div class="sidebar-header">
    <h1>SBEM UI</h1>
    <p class="subtitle">Building Energy Modeling Interface</p>
  </div>

  <nav class="sidebar-nav">
    {#each workflows as workflow}
      <button
        type="button"
        class="nav-item"
        class:active={currentWorkflow === workflow.id}
        onclick={() => setWorkflow(workflow.id)}
      >
        {workflow.label}
      </button>
    {/each}
  </nav>

  <div class="sidebar-footer">
    {#if $workspaceStore.workspace}
      <p class="project-name" title={$workspaceStore.workspace.path}>
        {$workspaceStore.workspace.name}
      </p>
      <button type="button" class="switch-project" onclick={() => workspaceStore.close()}>
        Switch project
      </button>
    {/if}
    <p class="version">v0.1.0</p>
  </div>
</aside>

<style>
  .sidebar {
    width: 260px;
    background: #f9fafb;
    border-right: 1px solid #e5e7eb;
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .sidebar-header {
    padding: 24px;
    border-bottom: 1px solid #e5e7eb;
  }

  .sidebar-header h1 {
    font-size: 20px;
    font-weight: 700;
    color: #111827;
    margin: 0 0 4px 0;
  }

  .subtitle {
    font-size: 13px;
    color: #6b7280;
    margin: 0;
  }

  .sidebar-nav {
    flex: 1;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .nav-item {
    display: block;
    width: 100%;
    padding: 12px 16px;
    border: none;
    background: transparent;
    border-radius: 8px;
    cursor: pointer;
    text-align: left;
    font-size: 14px;
    color: #374151;
    transition: all 0.15s ease;
  }

  .nav-item:hover {
    background: #f3f4f6;
  }

  .nav-item.active {
    background: #eff6ff;
    color: #2563eb;
    font-weight: 600;
  }

  .sidebar-footer {
    padding: 16px 24px;
    border-top: 1px solid #e5e7eb;
  }

  .version {
    font-size: 12px;
    color: #9ca3af;
    margin: 8px 0 0 0;
  }

  .project-name {
    font-size: 13px;
    font-weight: 600;
    color: #111827;
    margin: 0 0 6px 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .switch-project {
    width: 100%;
    padding: 6px 10px;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: #ffffff;
    color: #374151;
    font-size: 12px;
    cursor: pointer;
  }

  .switch-project:hover {
    background: #f3f4f6;
  }
</style>
