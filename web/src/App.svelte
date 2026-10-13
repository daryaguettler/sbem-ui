<script lang="ts">
  import { onMount } from 'svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import ProjectPicker from './lib/components/ProjectPicker.svelte';
  import SemanticFields from './lib/workflows/SemanticFields.svelte';
  import ComponentLibrary from './lib/workflows/ComponentLibrary.svelte';
  import ComponentMap from './lib/workflows/ComponentMap.svelte';
  import PriorTrees from './lib/workflows/PriorTrees.svelte';
  import Retrofits from './lib/workflows/Retrofits.svelte';
  import Sampling from './lib/workflows/Sampling.svelte';
  import GISCleaning from './lib/workflows/GISCleaning.svelte';
  import ModelExecution from './lib/workflows/ModelExecution.svelte';
  import ProjectFiles from './lib/workflows/ProjectFiles.svelte';
  import { currentWorkflow, navigateTo, restoreLastWorkflow } from './lib/stores/projectStore';
  import { workspaceStore } from './lib/stores/workspaceStore';
  import { componentTreeStore } from './lib/stores/componentTreeStore';
  import { resetProjectArtifacts, restoreProjectArtifacts } from './lib/stores/projectArtifacts';

  let checkingWorkspace = true;
  /** The project whose saved artifacts are currently in the editors, so opening the
   * same project twice doesn't reload it and switching projects always reloads. */
  let loadedProjectPath: string | null = null;

  $: syncOpenProject($workspaceStore.workspace?.path ?? null);

  async function syncOpenProject(path: string | null) {
    if (path === loadedProjectPath) return;
    loadedProjectPath = path;
    resetProjectArtifacts();
    if (path) {
      restoreLastWorkflow(path);
      await restoreProjectArtifacts();
    }
  }

  async function bootstrap() {
    checkingWorkspace = true;
    await componentTreeStore.load();
    await workspaceStore.tryReopenLastWorkspace();
    checkingWorkspace = false;
  }

  onMount(bootstrap);
</script>

{#if checkingWorkspace}
  <div class="boot-loading">Loading...</div>
{:else if $workspaceStore.backendUnreachable}
  <div class="boot-loading">
    <div class="unreachable">
      <p>{$workspaceStore.error}</p>
      <button type="button" onclick={bootstrap}>Retry</button>
    </div>
  </div>
{:else if !$workspaceStore.open}
  <ProjectPicker />
{:else}
  <main class="layout">
    <Sidebar currentWorkflow={$currentWorkflow} setWorkflow={navigateTo} />
    <section class="main">
      {#if $currentWorkflow === 'semantic-fields'}
        <SemanticFields />
      {:else if $currentWorkflow === 'component-library'}
        <ComponentLibrary />
      {:else if $currentWorkflow === 'component-map'}
        <ComponentMap />
      {:else if $currentWorkflow === 'prior-trees'}
        <PriorTrees />
      {:else if $currentWorkflow === 'retrofits'}
        <Retrofits />
      {:else if $currentWorkflow === 'sampling'}
        <Sampling />
      {:else if $currentWorkflow === 'gis-cleaning'}
        <GISCleaning />
      {:else if $currentWorkflow === 'model-execution'}
        <ModelExecution />
      {:else if $currentWorkflow === 'project-files'}
        <ProjectFiles />
      {/if}
    </section>
  </main>
{/if}

<style>
  /* Fixed to the viewport:the sidebar stays put and only .main scrolls. */
  .layout {
    display: flex;
    height: 100vh;
    overflow: hidden;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
  }

  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: auto;
  }

  .boot-loading {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: var(--text-muted);
    font-size: 14px;
  }

  .unreachable {
    max-width: 420px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  .unreachable button {
    padding: 8px 16px;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text);
    font-size: 14px;
    cursor: pointer;
  }

  .unreachable button:hover {
    background: var(--surface-3);
  }
</style>
