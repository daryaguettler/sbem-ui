<script lang="ts">
  import type { WorkflowId } from '../types/workflow';
  import { workspaceStore } from '../stores/workspaceStore';
  import { readinessChecks } from '../stores/projectStore';
  import { themeChoice, type ThemeChoice } from '../stores/theme';
  import { helpMode, type HelpMode } from '../stores/helpMode';

  export let currentWorkflow: WorkflowId;
  export let setWorkflow: (workflow: WorkflowId) => void;

  const steps: Array<{ id: WorkflowId; label: string }> = [
    { id: 'gis-cleaning', label: 'GIS Cleaning' },
    { id: 'characteristics', label: 'Building Characteristics' },
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

  const utilities: Array<{ id: WorkflowId; label: string; icon: string }> = [
    { id: 'component-library', label: 'Component Library', icon: '▦' },
    { id: 'project-files', label: 'Project Files', icon: '▤' },
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
              {#if check?.ready}<span aria-hidden="true">✓</span><span class="visually-hidden">Done:</span>{:else}{index + 1}{/if}
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
        <span class="step-badge utility-badge" aria-hidden="true">{utility.icon}</span>
        <span class="step-label">{utility.label}</span>
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

    <div class="theme-toggle" role="radiogroup" aria-label="Help text">
      {#each helpModes as mode}
        <button
          type="button"
          role="radio"
          aria-checked={$helpMode === mode.id}
          class:selected={$helpMode === mode.id}
          title={mode.title}
          onclick={() => helpMode.set(mode.id)}
        >
          {mode.label}
        </button>
      {/each}
    </div>

    <div class="theme-toggle" role="radiogroup" aria-label="Color theme">
      {#each themes as theme}
        <button
          type="button"
          role="radio"
          aria-checked={$themeChoice === theme.id}
          class:selected={$themeChoice === theme.id}
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
    background: var(--surface-2);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow-y: auto;
  }

  .sidebar-header {
    padding: 20px 20px 16px;
    border-bottom: 1px solid var(--border);
  }

  .sidebar-header h1 {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text);
    margin: 0;
  }

  .sidebar-nav {
    flex: 1;
    padding: 12px;
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
    gap: 10px;
    width: 100%;
    padding: 8px 10px;
    border: none;
    background: transparent;
    border-radius: var(--radius);
    cursor: pointer;
    text-align: left;
    font-size: 14px;
    color: var(--text-2);
    transition: background 0.15s ease;
  }

  .nav-item:hover {
    background: var(--surface-3);
  }

  .nav-item.active {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
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
    font-size: 11px;
    font-weight: 600;
  }

  .nav-item.active .step-badge {
    border-color: var(--accent);
    color: var(--accent);
  }

  /* Done = filled + check mark, so it doesn't rely on the green alone. */
  .step-badge.done {
    border-color: var(--ok);
    background: var(--ok);
    color: var(--on-accent);
  }

  .nav-item.active .step-badge.done {
    border-color: var(--ok);
    color: var(--on-accent);
  }

  .utility-badge {
    border-style: dashed;
  }

  .divider {
    height: 1px;
    margin: 10px 4px;
    background: var(--border);
  }

  .sidebar-footer {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px 20px 16px;
    border-top: 1px solid var(--border);
  }

  .version {
    font-size: 11px;
    color: var(--text-faint);
  }

  .project-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .switch-project {
    width: 100%;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text-2);
    font-size: 12px;
    cursor: pointer;
  }

  .switch-project:hover {
    background: var(--surface-3);
  }

  .theme-toggle {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-3);
  }

  .theme-toggle button {
    padding: 4px 0;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }

  .theme-toggle button.selected {
    background: var(--surface);
    color: var(--text);
    box-shadow: inset 0 0 0 1px var(--border-strong);
  }
</style>
