<script lang="ts">
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import ComponentMapGraph from '../components/componentMap/ComponentMapGraph.svelte';
  import ComponentMapTable from '../components/componentMap/ComponentMapTable.svelte';
  import ComponentSelectorEditor from '../components/componentMap/ComponentSelectorEditor.svelte';
  import { componentMapStore } from '../stores/componentMapStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import type { ComponentMapTemplateSummary } from '../types/componentMap';
  import { formatSavedAt, saveArtifact } from '../api/artifacts';
  import { loadSavedArtifact, markSaved, savedAt } from '../stores/projectArtifacts';
  import { downloadText } from '../utils/download';

  let templates: ComponentMapTemplateSummary[] = [];
  let loading = true;
  let error: string | null = null;
  let editorMode: 'browse' | 'edit' = 'browse';
  let saving = false;
  let checking = false;
  /** Result of resolving sampled semantic-field combinations against the component db. */
  let check: { ok: boolean; tested: number; failed: number; errors: string[] } | null = null;

  onMount(async () => {
    if ($componentMapStore.map) {
      editorMode = 'edit';
    }
    await loadTemplates();
  });

  async function loadTemplates() {
    loading = true;
    error = null;
    try {
      const response = await fetch('/api/component-map/templates');
      const data = await response.json();
      templates = data.templates || [];
    } catch (e) {
      error = 'Failed to load component map templates.';
    } finally {
      loading = false;
    }
  }

  async function loadTemplate(filename: string) {
    try {
      const response = await fetch(`/api/component-map/templates/${filename}`);
      const templateData = await response.json();
      componentMapStore.loadFromTemplate(templateData, filename);
      componentMapStore.setSelectedPath('Envelope');
      editorMode = 'edit';
    } catch (e) {
      error = 'Failed to load template.';
    }
  }

  function startFromScratch() {
    componentMapStore.startFromScratch();
    editorMode = 'edit';
  }

  async function validateMap() {
    if (!$componentMapStore.map) {
      error = 'Load a component map first.';
      return;
    }

    const response = await fetch('/api/component-map/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        component_map: $componentMapStore.map,
        semantic_fields: $semanticFieldsStore.fields.map((field) => ({
          name: field.name,
          options: field.options,
        })),
      }),
    });

    const data = await response.json();
    componentMapStore.setValidation(data.valid, data.errors || [], data.generated_names || []);
  }

  async function saveToProject() {
    if (!$componentMapStore.map) return;
    saving = true;
    error = null;
    try {
      const file = await saveArtifact('component-map', $componentMapStore.map);
      markSaved('component-map', file.modifiedAt);
      check = null;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to save to the project.';
    } finally {
      saving = false;
    }
  }

  /** Save, then resolve sampled combinations of the saved globi map against the library. */
  async function checkAgainstLibrary() {
    await saveToProject();
    if (error) return;
    checking = true;
    try {
      const response = await fetch('/api/component-map/check', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail ?? 'Check failed.');
      check = data;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Check failed.';
    } finally {
      checking = false;
    }
  }

  /** Discard unsaved edits and read the project's saved selector declarations back in. */
  async function loadFromProject() {
    error = null;
    try {
      if (!(await loadSavedArtifact('component-map'))) {
        error = 'No component map has been saved in this project yet.';
        return;
      }
      componentMapStore.setSelectedPath('Envelope');
      editorMode = 'edit';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load the saved component map.';
    }
  }

  async function exportMap() {
    if (!$componentMapStore.map) return;

    const response = await fetch('/api/component-map/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        component_map: $componentMapStore.map,
        semantic_fields: $semanticFieldsStore.fields,
      }),
    });

    downloadText(await response.text(), 'component-map.yml', 'application/x-yaml');
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Component Map</h1>
    <p class="subtitle">Connect semantic fields to building components at any hierarchy level</p>
  </div>

  <div class="workflow-content">
    {#if $semanticFieldsStore.fields.length === 0}
      <WorkflowGuide
        title="Define semantic fields first"
        message="Component selectors reference semantic field names. Create or load semantic fields before mapping components."
        actionLabel="Go to Semantic Fields"
        actionWorkflow="semantic-fields"
      />
    {:else if editorMode === 'browse'}
      <div class="panel">
        <h2>Choose a starting point</h2>
        {#if loading}
          <p>Loading templates...</p>
        {:else}
          <div class="templates-grid">
            {#each templates as template}
              <button type="button" class="template-card" onclick={() => loadTemplate(template.filename)}>
                <h3>{template.name}</h3>
                {#if template.description}<p>{template.description}</p>{/if}
              </button>
            {/each}
            {#if $savedAt['component-map']}
              <button type="button" class="template-card saved" onclick={loadFromProject}>
                <h3>Saved in this project</h3>
                <p>{formatSavedAt($savedAt['component-map'])}.</p>
              </button>
            {/if}
            <button type="button" class="template-card scratch" onclick={startFromScratch}>
              <h3>Start from scratch</h3>
              <p>Every component, no selectors yet.</p>
            </button>
          </div>
        {/if}
      </div>
    {:else}
      <div class="toolbar panel">
        <div class="view-toggle">
          <button
            type="button"
            class:active={$componentMapStore.viewMode === 'graph'}
            onclick={() => componentMapStore.setViewMode('graph')}
          >
            Graph
          </button>
          <button
            type="button"
            class:active={$componentMapStore.viewMode === 'table'}
            onclick={() => componentMapStore.setViewMode('table')}
          >
            Table
          </button>
        </div>
        <div class="toolbar-actions">
          <button type="button" class="secondary" onclick={() => (editorMode = 'browse')}>Change template</button>
          <button type="button" onclick={saveToProject} disabled={saving || !$componentMapStore.map}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          {#if $savedAt['component-map']}
            <button type="button" class="secondary" onclick={loadFromProject}>Revert</button>
          {/if}
          <button type="button" class="secondary" onclick={validateMap} title="Check that every selector refers to an existing semantic field">Validate</button>
          <button
            type="button"
            class="secondary"
            onclick={checkAgainstLibrary}
            disabled={checking || saving || !$componentMapStore.map}
            title="Saves the map, then checks that a random sample of field combinations each find a record in the Component Library"
          >
            {checking ? 'Checking…' : 'Save & check library'}
          </button>
          <button type="button" class="secondary" onclick={exportMap} disabled={!$componentMapStore.map}>Export YAML</button>
        </div>
      </div>

      <p class="saved-status">
        {formatSavedAt($savedAt['component-map'])}
        {#if check}
          · <span class:check-ok={check.ok} class:check-bad={!check.ok}>
            <span aria-hidden="true">{check.ok ? '✓' : '✕'}</span>
            {check.ok
              ? `Library check passed: ${check.tested} sampled combinations all found a record`
              : `Library check: ${check.failed} of ${check.tested} sampled combinations have no record. ${check.errors[0] ?? ''}`}
          </span>
        {/if}
      </p>

      <div class="editor-layout">
        <section class="main-panel panel">
          {#if $componentMapStore.viewMode === 'graph'}
            <ComponentMapGraph />
            <p class="help">Drag from semantic fields to components, or click a component node to edit its selector.</p>
          {:else}
            <ComponentMapTable />
          {/if}
        </section>

        <aside class="side-panel panel">
          <h2>Selector editor</h2>
          {#if $componentMapStore.selectedPath}
            <ComponentSelectorEditor path={$componentMapStore.selectedPath} />
          {:else}
            <p class="help">Select a component in the graph or table to configure source fields and suffix.</p>
          {/if}
        </aside>
      </div>

      {#if $componentMapStore.validationErrors.length > 0}
        <div class="panel invalid">
          <ul>
            {#each $componentMapStore.validationErrors as issue}
              <li>{issue}</li>
            {/each}
          </ul>
        </div>
      {:else if $componentMapStore.valid}
        <div class="panel success">
          <p>Component map is valid.</p>
          {#if $componentMapStore.generatedNames.length > 0}
            <p>{ $componentMapStore.generatedNames.length } generated component names.</p>
            <details>
              <summary>Preview names</summary>
              <ul>
                {#each $componentMapStore.generatedNames.slice(0, 20) as name}
                  <li>{name}</li>
                {/each}
              </ul>
            </details>
          {/if}
        </div>
      {/if}
    {/if}

    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>
</section>

<style>
  .workflow {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .workflow-header {
    padding: 24px 32px;
    border-bottom: 1px solid var(--border);
  }

  .workflow-header h1 {
    margin: 0 0 4px;
    font-size: 24px;
  }

  .subtitle,
  .help {
    margin: 0;
    color: var(--text-muted);
    font-size: 14px;
  }

  .help {
    margin-top: 12px;
  }

  .workflow-content {
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .panel {
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    background: var(--surface);
  }

  .panel h2 {
    margin: 0 0 12px;
    font-size: 18px;
    color: var(--text);
  }

  .templates-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  .template-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    background: var(--surface);
    color: var(--text);
    font-weight: 400;
    text-align: left;
    cursor: pointer;
  }

  .template-card h3 {
    margin: 0 0 8px;
    font-size: 16px;
    color: var(--text);
  }

  .template-card p {
    margin: 0;
    color: var(--text-muted);
    font-size: 13px;
  }

  .template-card.scratch {
    border-style: dashed;
    background: var(--surface-2);
  }

  .template-card.saved {
    border-color: var(--accent-border);
    background: var(--accent-soft);
  }

  .check-ok { color: var(--ok-text); font-weight: 600; }
  .check-bad { color: var(--err-text); font-weight: 600; }

  .saved-status {
    margin: -16px 0 0;
    font-size: 13px;
    color: var(--text-muted);
  }

  .toolbar {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
  }

  .view-toggle,
  .toolbar-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .view-toggle button,
  .toolbar-actions button {
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text-2);
    padding: 8px 12px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
  }

  .view-toggle button.active {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }

  .toolbar-actions button {
    background: var(--accent);
    color: var(--on-accent);
    border-color: var(--accent);
  }

  .toolbar-actions .secondary {
    background: var(--surface);
    color: var(--accent);
  }

  .editor-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
    gap: 16px;
  }

  .main-panel,
  .side-panel {
    min-height: 560px;
  }

  .invalid {
    border-color: var(--err-border);
    background: var(--err-bg);
    color: var(--err-text);
  }

  .success {
    border-color: var(--ok-border);
    background: var(--ok-bg);
    color: var(--ok-text);
  }

  .error {
    color: var(--err-text);
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @media (max-width: 1100px) {
    .editor-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
