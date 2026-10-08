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
      A project is a folder on disk holding your semantic fields, component library, component
      map, and priors -- so your work survives closing the browser.
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
        <p class="error">{$workspaceStore.error}</p>
      {/if}

      <button type="submit" class="submit" disabled={$workspaceStore.loading || !path.trim()}>
        {$workspaceStore.loading ? 'Working...' : mode === 'create' ? 'Create project' : 'Open project'}
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
    background: #f9fafb;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }

  .card {
    width: 420px;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 32px;
  }

  h1 {
    font-size: 20px;
    font-weight: 700;
    color: #111827;
    margin: 0 0 8px 0;
  }

  .subtitle {
    font-size: 13px;
    color: #6b7280;
    margin: 0 0 24px 0;
    line-height: 1.5;
  }

  .mode-toggle {
    display: flex;
    gap: 4px;
    background: #f3f4f6;
    border-radius: 8px;
    padding: 4px;
    margin-bottom: 20px;
  }

  .mode-toggle button {
    flex: 1;
    padding: 8px 12px;
    border: none;
    background: transparent;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    color: #6b7280;
  }

  .mode-toggle button.active {
    background: #ffffff;
    color: #111827;
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
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
    color: #374151;
  }

  input {
    font-weight: 400;
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
  }

  .error {
    margin: 0;
    font-size: 13px;
    color: #dc2626;
  }

  .submit {
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }

  .submit:disabled {
    background: #93c5fd;
    cursor: not-allowed;
  }
</style>
