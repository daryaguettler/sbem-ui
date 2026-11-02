<script lang="ts">
  import { onMount } from 'svelte';
  import { workspaceStore } from '../stores/workspaceStore';
  import { startTutorial, tutorialOn } from '../stores/tutorial';
  import Select from './Select.svelte';

  let mode: 'create' | 'open' = 'create';
  let path = '';
  let name = 'My Project';
  let templates: Array<{ name: string; filename: string; description: string }> = [];
  let template = '';
  /** sbem-ui/data: new projects go in a subfolder named after the project unless the user types a path. */
  let projectsDir = '';
  let pathEdited = false;

  const slug = (text: string) =>
    text.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'my-project';
  $: if (!pathEdited) path = mode === 'create' && projectsDir ? `${projectsDir}/${slug(name)}` : '';

  onMount(async () => {
    try {
      templates = (await (await fetch('/api/workspace/templates')).json()).templates ?? [];
    } catch {
      templates = [];
    }
    try {
      projectsDir = (await (await fetch('/api/workspace/defaults')).json()).projectsDir ?? '';
    } catch {
      projectsDir = '';
    }
  });

  async function submit() {
    if (!path.trim()) return;
    if (mode === 'create') {
      await workspaceStore.create(path.trim(), name.trim() || 'My Project', template || null);
    } else {
      await workspaceStore.open(path.trim());
    }
  }
</script>

<div class="picker">
  <div class="card">
    <h1>Open a project</h1>
    <p class="subtitle">
      A project is a folder on disk holding your building characteristics, their estimates and
      model parts, and the component library -- so your work survives closing the browser.
    </p>
    {#if !$tutorialOn}
      <p class="hint">
        New here?
        <button type="button" class="btn btn-link" onclick={() => { mode = 'create'; startTutorial(); }}>Take the tutorial</button>
        from a new project to globi's run files.
      </p>
    {/if}

    <div class="segmented" role="group" aria-label="Project mode">
      <button type="button" aria-pressed={mode === 'create'} onclick={() => (mode = 'create')}>
        Create new
      </button>
      <button type="button" aria-pressed={mode === 'open'} onclick={() => (mode = 'open')}>
        Open existing
      </button>
    </div>

    <form onsubmit={(event) => { event.preventDefault(); submit(); }}>
      {#if mode === 'create'}
        <label class="field" data-tour="picker-name">
          Project name
          <input type="text" bind:value={name} placeholder="My Project" />
        </label>
        {#if templates.length > 0}
          <div class="field" data-tour="template">
            <span>Component library</span>
            <Select
              value={template}
              options={[{ value: '', label: 'Empty' }, ...templates.map((t) => ({ value: t.filename, label: t.name }))]}
              onChange={(value) => (template = value)}
              ariaLabel="Component library"
            />
            {#if template}
              <span class="hint">{templates.find((t) => t.filename === template)?.description}</span>
            {/if}
          </div>
        {/if}
      {/if}
      <label class="field" data-tour="picker-path">
        Folder path
        <input type="text" bind:value={path} oninput={() => (pathEdited = true)} placeholder="/Users/you/sbem-projects/my-project" />
        {#if mode === 'create'}
          <span class="hint">To run batches or Single Building, use a folder in globi's inputs/ instead.</span>
        {/if}
      </label>

      {#if $workspaceStore.error}
        <p class="error" role="alert">{$workspaceStore.error}</p>
      {/if}

      <button type="submit" class="btn" disabled={$workspaceStore.loading || !path.trim()}>
        {$workspaceStore.loading ? (mode === 'create' ? 'Creating…' : 'Opening…') : mode === 'create' ? 'Create project' : 'Open project'}
      </button>
    </form>
  </div>
</div>

<style>
  .picker {
    min-height: 100vh;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--surface-2);
  }

  .card {
    width: 420px;
    max-width: calc(100% - 2 * var(--space-4));
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-8);
  }

  h1 {
    font-size: var(--text-xl);
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--text);
    margin-bottom: var(--space-2);
  }

  .subtitle {
    font-size: var(--text-sm);
    color: var(--text-muted);
    margin-bottom: var(--space-6);
  }

  .segmented {
    display: flex;
    margin-bottom: var(--space-5);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
</style>
