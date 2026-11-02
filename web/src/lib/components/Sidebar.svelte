<script lang="ts">
  import type { WorkflowId } from '../types/workflow';
  import { workspaceStore } from '../stores/workspaceStore';
  import { readinessChecks } from '../stores/projectStore';
  import { themeChoice, type ThemeChoice } from '../stores/theme';
  import { helpMode, type HelpMode } from '../stores/helpMode';
  import { startTutorial, tutorialOn } from '../stores/tutorial';
  import Icon, { type IconName } from './Icon.svelte';

  export let currentWorkflow: WorkflowId;
  export let setWorkflow: (workflow: WorkflowId) => void;

  // Characteristics come first and are complete on their own; Component Map then decides what depends on them.
  const steps: Array<{ id: WorkflowId; label: string }> = [
    { id: 'gis-cleaning', label: 'GIS Cleaning' },
    { id: 'characteristics', label: 'Building Characteristics' },
    { id: 'model-parts', label: 'Component Map' },
    { id: 'retrofits', label: 'Retrofits' },
    { id: 'sampling', label: 'Sampling' },
    { id: 'model-execution', label: 'Model Execution' },
  ];

  const themes: Array<{ id: ThemeChoice; label: string }> = [
    { id: 'light', label: 'Light' },
    { id: 'dark', label: 'Dark' },
    { id: 'system', label: 'System' },
  ];

  const helpModes: Array<{ id: HelpMode; label: string; title: string }> = [
    { id: 'minimal', label: 'Minimal', title: 'Controls only; guidance sits behind each ?' },
    { id: 'explain', label: 'Explain', title: 'Show how-to guidance under every section' },
  ];

  const utilities: Array<{ id: WorkflowId; label: string; icon: IconName }> = [
    { id: 'component-library', label: 'Component Library', icon: 'grid' },
    { id: 'single-building', label: 'Single Building', icon: 'home' },
    { id: 'project-files', label: 'Project Files', icon: 'file' },
  ];

  // Only the steps with readiness checks get a done/not-done mark; a step with several
  // checks (Building Characteristics) is done when all of them are.
  $: checksFor = (workflow: WorkflowId) => $readinessChecks.filter((check) => check.workflow === workflow);
  $: stepChecks = new Map(
    steps.map((step) => {
      const checks = checksFor(step.id);
      return [
        step.id,
        checks.length
          ? {
              ready: checks.every((check) => check.ready),
              detail: checks.filter((check) => !check.ready).map((check) => check.detail).join(' '),
            }
          : null,
      ];
    })
  );
</script>

<aside class="sidebar">
  <div class="sidebar-header">
    <h1>SBEM UI</h1>
  </div>

  <nav class="sidebar-nav" aria-label="Workflow steps">
    <ol class="steps">
      {#each steps as step, index}
        {@const check = stepChecks.get(step.id)}
        <li>
          <button
            type="button"
            class="nav-item"
            class:active={currentWorkflow === step.id}
            aria-current={currentWorkflow === step.id ? 'page' : undefined}
            title={check?.detail}
            onclick={() => setWorkflow(step.id)}
          >
            <span class="step-badge" class:done={check?.ready}>
              {#if check?.ready}<Icon name="check" size={12} /><span class="visually-hidden">Done:</span>{:else}{index + 1}{/if}
            </span>
            <span class="step-label">{step.label}</span>
          </button>
        </li>
      {/each}
    </ol>

    <div class="divider" role="separator"></div>

    {#each utilities as utility}
      <button
        type="button"
        class="nav-item utility"
        class:active={currentWorkflow === utility.id}
        aria-current={currentWorkflow === utility.id ? 'page' : undefined}
        onclick={() => setWorkflow(utility.id)}
      >
        <span class="step-badge utility-badge"><Icon name={utility.icon} /></span>
        <span class="step-label">{utility.label}</span>
      </button>
    {/each}
  </nav>

  <div class="sidebar-footer">
    {#if $workspaceStore.workspace}
      <p class="project-name" title={$workspaceStore.workspace.path}>
        {$workspaceStore.workspace.name}
      </p>
      <button type="button" class="btn btn-secondary btn-sm" onclick={() => workspaceStore.close()}>
        Switch project
      </button>
    {/if}

    <button
      type="button"
      class="btn btn-secondary btn-sm"
      aria-pressed={$tutorialOn}
      onclick={() => ($tutorialOn ? tutorialOn.set(false) : startTutorial())}
    >
      {$tutorialOn ? 'Exit tutorial' : 'Tutorial'}
    </button>

    <div class="segmented" role="group" aria-label="Help text">
      {#each helpModes as mode}
        <button
          type="button"
          aria-pressed={$helpMode === mode.id}
          title={mode.title}
          onclick={() => helpMode.set(mode.id)}
        >
          {mode.label}
        </button>
      {/each}
    </div>

    <div class="segmented" role="group" aria-label="Color theme">
      {#each themes as theme}
        <button
          type="button"
          aria-pressed={$themeChoice === theme.id}
          onclick={() => themeChoice.set(theme.id)}
        >
          {theme.label}
        </button>
      {/each}
    </div>

    <p class="version">v0.1.0</p>
  </div>
</aside>

<style>
  .sidebar {
    width: 248px;
    flex: none;
    background: var(--bg);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow-y: auto;
  }

  /* Same height as .workflow-header (one h1 line), so the two bottom rules meet. */
  .sidebar-header {
    display: flex;
    align-items: center;
    min-height: calc(var(--text-xl) * 1.25 + 2 * var(--space-5) + 1px);
    padding: 0 var(--space-5);
    border-bottom: 1px solid var(--border);
  }

  .sidebar-header h1 {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text);
  }

  .sidebar-nav {
    flex: 1;
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .steps {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border: none;
    background: transparent;
    border-radius: var(--radius);
    cursor: pointer;
    text-align: left;
    font-size: var(--text-md);
    color: var(--text-2);
    transition: background 0.15s ease;
  }

  .nav-item:hover,
  .nav-item.active {
    background: var(--surface-3);
  }

  .nav-item.active {
    color: var(--text);
    font-weight: 500;
  }

  .step-badge {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .nav-item.active .step-badge {
    border-color: var(--text-muted);
    color: var(--text);
  }

  /* Done = filled + check mark, so it doesn't rely on the green alone. */
  .step-badge.done,
  .nav-item.active .step-badge.done {
    border-color: var(--ok);
    background: var(--ok);
    color: var(--on-accent);
  }

  .utility-badge,
  .nav-item.active .utility-badge {
    border-color: transparent;
    background: transparent;
  }

  .divider {
    height: 1px;
    margin: var(--space-3) var(--space-1);
    background: var(--border);
  }

  .sidebar-footer {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-4) var(--space-5);
    border-top: 1px solid var(--border);
  }

  .version {
    font-size: var(--text-2xs);
    color: var(--text-faint);
  }

  .project-name {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
