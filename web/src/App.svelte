<script lang="ts">
  import { onMount } from 'svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import ProjectPicker from './lib/components/ProjectPicker.svelte';
  import BuildingCharacteristics from './lib/workflows/BuildingCharacteristics.svelte';
  import ModelParts from './lib/workflows/ModelParts.svelte';
  import ComponentLibrary from './lib/workflows/ComponentLibrary.svelte';
  import Retrofits from './lib/workflows/Retrofits.svelte';
  import Sampling from './lib/workflows/Sampling.svelte';
  import GISCleaning from './lib/workflows/GISCleaning.svelte';
  import ModelExecution from './lib/workflows/ModelExecution.svelte';
  import ProjectFiles from './lib/workflows/ProjectFiles.svelte';
  import SingleBuilding from './lib/workflows/SingleBuilding.svelte';
  import { currentWorkflow, navigateTo, restoreLastWorkflow } from './lib/stores/projectStore';
  import { workspaceStore } from './lib/stores/workspaceStore';
  import { componentTreeStore } from './lib/stores/componentTreeStore';
  import { resetProjectArtifacts, restoreProjectArtifacts } from './lib/stores/projectArtifacts';
  import TutorialPanel from './lib/components/TutorialPanel.svelte';
  import { tutorialMarks, tutorialOn } from './lib/stores/tutorial';

  let checkingWorkspace = true;
  /** The project whose saved artifacts are currently in the editors, so opening the
   * same project twice doesn't reload it and switching projects always reloads. */
  let loadedProjectPath: string | null = null;

  $: syncOpenProject($workspaceStore.workspace?.path ?? null);

  async function syncOpenProject(path: string | null) {
    if (path === loadedProjectPath) return;
    loadedProjectPath = path;
    resetProjectArtifacts();
    tutorialMarks.set({ sampling: false, runFiles: false });
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
  <div class="boot-loading">Loading…</div>
{:else if $workspaceStore.backendUnreachable}
  <div class="boot-loading">
    <div class="unreachable">
      <p>{$workspaceStore.error}</p>
      <button type="button" class="btn btn-secondary" onclick={bootstrap}>Retry</button>
    </div>
  </div>
{:else if !$workspaceStore.open}
  <ProjectPicker />
{:else}
  <main class="layout">
    <Sidebar currentWorkflow={$currentWorkflow} setWorkflow={navigateTo} />
    <section class="main">
      {#if $currentWorkflow === 'model-parts'}
        <ModelParts />
      {:else if $currentWorkflow === 'characteristics'}
        <BuildingCharacteristics />
      {:else if $currentWorkflow === 'component-library'}
        <ComponentLibrary />
      {:else if $currentWorkflow === 'retrofits'}
        <Retrofits />
      {:else if $currentWorkflow === 'sampling'}
        <Sampling />
      {:else if $currentWorkflow === 'gis-cleaning'}
        <GISCleaning />
      {:else if $currentWorkflow === 'model-execution'}
        <ModelExecution />
      {:else if $currentWorkflow === 'single-building'}
        <SingleBuilding />
      {:else if $currentWorkflow === 'project-files'}
        <ProjectFiles />
      {/if}
    </section>
  </main>
{/if}

{#if $tutorialOn && !checkingWorkspace && !$workspaceStore.backendUnreachable}<TutorialPanel />{/if}

<style>
  /* Fixed to the viewport:the sidebar stays put and only .main scrolls. */
  .layout {
    display: flex;
    height: 100vh;
    overflow: hidden;
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
    color: var(--text-muted);
    font-size: var(--text-md);
  }

  .unreachable {
    max-width: 420px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-3);
  }
</style>
