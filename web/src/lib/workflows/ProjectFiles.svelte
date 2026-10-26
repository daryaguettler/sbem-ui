<script lang="ts">
  import {
    fetchWorkspaceFileContent,
    fetchWorkspaceFiles,
    formatFileSize,
    formatRelativeTime,
    type ArtifactKind,
    type WorkspaceFile,
    type WorkspaceFileContent,
  } from '../api/artifacts';
  import { loadSavedArtifact } from '../stores/projectArtifacts';
  import { navigateTo } from '../stores/projectStore';
  import { workspaceStore } from '../stores/workspaceStore';
  import type { WorkflowId } from '../types/workflow';
  import { downloadText } from '../utils/download';
  import Explain from '../components/Explain.svelte';
  import { HELP } from '../help';
  const help = HELP.projectFiles;

  const WORKFLOW_FOR_KIND: Record<ArtifactKind, WorkflowId> = {
    'semantic-fields': 'characteristics',
    'component-map': 'characteristics',
    priors: 'characteristics',
    retrofits: 'retrofits',
  };

  let root = $state('');
  let files = $state<WorkspaceFile[]>([]);
  let selected = $state<WorkspaceFileContent | null>(null);
  let loadingFiles = $state(true);
  let loadingContent = $state(false);
  let error = $state<string | null>(null);

  async function loadFiles(keepSelection = true) {
    loadingFiles = true;
    error = null;
    try {
      const listing = await fetchWorkspaceFiles();
      root = listing.root;
      files = listing.files;

      const stillThere = selected && files.some((file) => file.path === selected!.path);
      if (keepSelection && stillThere) {
        await openFile(selected!.path);
      } else {
        selected = null;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to list project files.';
    } finally {
      loadingFiles = false;
    }
  }

  async function openFile(path: string) {
    loadingContent = true;
    error = null;
    try {
      selected = await fetchWorkspaceFileContent(path);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to read file.';
    } finally {
      loadingContent = false;
    }
  }

  async function loadIntoEditor(kind: ArtifactKind) {
    error = null;
    try {
      const loaded = await loadSavedArtifact(kind);
      if (!loaded) {
        error = 'That file is empty -- there is nothing to load yet.';
        return;
      }
      navigateTo(WORKFLOW_FOR_KIND[kind]);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load the file into its editor.';
    }
  }

  function downloadSelected() {
    if (!selected?.content) return;
    downloadText(selected.content, selected.name, 'text/plain');
  }

  loadFiles();
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Project Files <Explain text={help.page} tip /></h1>
    <Explain text={help.page} />
  </div>

  <div class="workflow-content">
    <div class="toolbar panel">
      <p class="path" title={root}>{$workspaceStore.workspace?.name ?? 'Project'} &mdash; {root}</p>
      <div class="toolbar-actions">
        <button type="button" class="btn btn-secondary" onclick={() => loadFiles()}>Refresh</button>
      </div>
    </div>

    {#if error}
      <p class="error" role="alert">{error}</p>
    {/if}

    <div class="browser">
      <aside class="file-list panel">
        {#if loadingFiles}
          <p class="help">Loading files…</p>
        {:else if files.length === 0}
          <p class="help">This project directory is empty.</p>
        {:else}
          {#each files as file (file.path)}
            <button
              type="button"
              class="file-row"
              class:active={selected?.path === file.path}
              onclick={() => openFile(file.path)}
            >
              <span class="file-name">
                {file.path}
                {#if file.kind}<span class="badge">{file.label}</span>{/if}
              </span>
              <span class="file-meta">
                {formatFileSize(file.size)} &middot; {formatRelativeTime(file.modifiedAt)}
              </span>
            </button>
          {/each}
        {/if}
      </aside>

      <section class="viewer panel">
        {#if loadingContent}
          <p class="help">Reading file…</p>
        {:else if !selected}
          <p class="help">Select a file to view its contents.</p>
        {:else}
          <div class="viewer-header">
            <h2>{selected.path}</h2>
            <div class="toolbar-actions">
              {#if selected.kind}
                <button type="button" class="btn" onclick={() => loadIntoEditor(selected!.kind!)}>
                  Load into editor
                </button>
              {/if}
              <button
                type="button"
                class="btn btn-secondary"
                onclick={downloadSelected}
                disabled={!selected.content}
              >
                Download
              </button>
            </div>
          </div>

          {#if !selected.viewable}
            <p class="help">
              {selected.name} is a binary file ({formatFileSize(selected.size)}) and can't be shown here.
            </p>
          {:else}
            {#if selected.truncated}
              <p class="truncated">
                Showing the first {formatFileSize(selected.content?.length ?? 0)} of
                {formatFileSize(selected.size)}. Download gives you the same portion.
              </p>
            {/if}
            <pre>{selected.content}</pre>
          {/if}
        {/if}
      </section>
    </div>
  </div>
</section>

<style>
  .help {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .workflow-content {
    min-height: 0;
  }

  .toolbar {
    flex-direction: row;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
  }

  .path {
    margin: 0;
    font-size: 13px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .toolbar-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .browser {
    display: grid;
    grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
    gap: 24px;
    align-items: start;
  }

  .file-list {
    gap: 4px;
    padding: 12px;
    max-height: 70vh;
    overflow: auto;
  }

  .file-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
    text-align: left;
    padding: 10px 12px;
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--text);
    font: inherit;
    cursor: pointer;
  }

  .file-row:hover {
    background: var(--surface-3);
  }

  .file-row.active {
    background: var(--accent-soft);
  }

  .file-name {
    font-size: 13px;
    color: var(--text);
    font-family: var(--font-mono);
    word-break: break-all;
  }

  .file-meta {
    font-size: 12px;
    color: var(--text-muted);
  }

  .badge {
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    background: var(--accent-soft);
    color: var(--accent-hover);
    font-size: 11px;
    font-family: var(--font-sans);
    white-space: nowrap;
  }

  .viewer {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }

  .viewer-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }

  .viewer-header h2 {
    margin: 0;
    font-size: 16px;
    color: var(--text);
    font-family: var(--font-mono);
    word-break: break-all;
  }

  pre {
    margin: 0;
    padding: 16px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 12px;
    line-height: 1.6;
    max-height: 60vh;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .truncated {
    margin: 0;
    font-size: 13px;
    color: var(--warn-text);
    background: var(--warn-bg);
    border: 1px solid var(--warn-border);
    border-radius: var(--radius);
    padding: 8px 12px;
  }

  @media (max-width: 1100px) {
    .browser {
      grid-template-columns: 1fr;
    }
  }
</style>
