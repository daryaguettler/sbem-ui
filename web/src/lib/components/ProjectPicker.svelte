<script lang="ts">
  import { workspaceStore } from '../stores/workspaceStore';

  let mode: 'create' | 'open' = 'create';
  let path = '';
  let name = 'My Project';

  async function submit() {
    if (!path.trim()) return;
    if (mode === 'create') {
      await workspaceStore.create(path.trim(), name.trim() || 'My Project');
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

    <div class="mode-toggle">
      <button type="button" class:active={mode === 'create'} onclick={() => (mode = 'create')}>
        Create new
      </button>
      <button type="button" class:active={mode === 'open'} onclick={() => (mode = 'open')}>
        Open existing
      </button>
    </div>

    <form onsubmit={(event) => { event.preventDefault(); submit(); }}>
      {#if mode === 'create'}
        <label>
          Project name
          <input type="text" bind:value={name} placeholder="My Project" />
        </label>
      {/if}
      <label>
        Folder path
        <input type="text" bind:value={path} placeholder="/Users/you/sbem-projects/my-project" />
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
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 32px;
  }

  h1 {
    font-size: 20px;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 8px 0;
  }

  .subtitle {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0 0 24px 0;
    line-height: 1.5;
  }

  .mode-toggle {
    display: flex;
    gap: 4px;
    background: var(--surface-3);
    border-radius: var(--radius);
    padding: 4px;
    margin-bottom: 20px;
  }

  .mode-toggle button {
    flex: 1;
    padding: 8px 12px;
    border: none;
    background: transparent;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 13px;
    color: var(--text-muted);
  }

  .mode-toggle button.active {
    background: var(--surface);
    color: var(--text);
    font-weight: 600;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-2);
  }

  input {
    font-weight: 400;
    padding: 8px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    font-size: 14px;
  }

  .error {
    margin: 0;
    font-size: 13px;
    color: var(--err-text);
  }

</style>
