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
    'part-rules': 'model-parts',
    priors: 'characteristics',
    retrofits: 'retrofits',
    'schedule-variability': 'component-library',
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
      <div class="actions">
        <button type="button" class="btn btn-secondary" onclick={() => loadFiles()}>Refresh</button>
      </div>
    </div>

    {#if error}
      <p class="error" role="alert">{error}</p>
    {/if}

    <div class="browser">
      <aside class="file-list panel">
        {#if loadingFiles}
          <p class="hint">Loading files…</p>
        {:else if files.length === 0}
          <p class="hint">This project directory is empty.</p>
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
                {#if file.kind}<span class="tag">{file.label}</span>{/if}
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
          <p class="hint">Reading file…</p>
        {:else if !selected}
          <p class="hint">Select a file to view its contents.</p>
        {:else}
          <div class="viewer-header">
            <h2>{selected.path}</h2>
            <div class="actions">
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
            <p class="hint">
              {selected.name} is a binary file ({formatFileSize(selected.size)}) and can't be shown here.
            </p>
          {:else}
            {#if selected.truncated}
              <p class="callout callout-warn">
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
  .workflow-content {
    min-height: 0;
  }

  .toolbar {
    flex-direction: row;
    justify-content: space-between;
    gap: var(--space-4);
    flex-wrap: wrap;
    align-items: center;
  }

  .path {
    font-size: var(--text-sm);
    color: var(--text-muted);
    font-family: var(--font-mono);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .browser {
    display: grid;
    grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
    gap: var(--space-6);
    align-items: start;
  }

  .file-list {
    gap: var(--space-1);
    padding: var(--space-3);
    max-height: 70vh;
    overflow: auto;
  }

  .file-row {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    width: 100%;
    text-align: left;
    padding: var(--space-2) var(--space-3);
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--text);
    cursor: pointer;
  }

  .file-row:hover,
  .file-row.active {
    background: var(--surface-3);
  }

  .file-name {
    font-size: var(--text-sm);
    color: var(--text);
    word-break: break-all;
  }

  .file-row.active .file-name {
    font-weight: 500;
  }

  .file-name .tag {
    margin-left: var(--space-2);
  }

  .file-meta {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .viewer {
    min-width: 0;
  }

  .viewer-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    flex-wrap: wrap;
  }

  .viewer-header h2 {
    word-break: break-all;
  }

  pre {
    padding: var(--space-4);
    background: var(--surface-2);
    border-radius: var(--radius);
    font-size: var(--text-xs);
    line-height: 1.6;
    max-height: 60vh;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  @media (max-width: 1100px) {
    .browser {
      grid-template-columns: 1fr;
    }
  }
</style>
