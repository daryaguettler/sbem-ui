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

  const WORKFLOW_FOR_KIND: Record<ArtifactKind, WorkflowId> = {
    'semantic-fields': 'semantic-fields',
    'component-map': 'component-map',
    priors: 'prior-trees',
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
    <h1>Project Files</h1>
    <p class="subtitle">
      Everything saved in this project on disk. Open a file to read it, or load a saved artifact
      straight back into its editor.
    </p>
  </div>

  <div class="workflow-content">
    <div class="toolbar panel">
      <p class="path" title={root}>{$workspaceStore.workspace?.name ?? 'Project'} &mdash; {root}</p>
      <div class="toolbar-actions">
        <button type="button" onclick={() => loadFiles()}>Refresh</button>
      </div>
    </div>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    <div class="browser">
      <aside class="file-list panel">
        {#if loadingFiles}
          <p class="help">Loading files...</p>
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
          <p class="help">Reading file...</p>
        {:else if !selected}
          <p class="help">Select a file to view its contents.</p>
        {:else}
          <div class="viewer-header">
            <h2>{selected.path}</h2>
            <div class="toolbar-actions">
              {#if selected.kind}
                <button type="button" onclick={() => loadIntoEditor(selected!.kind!)}>
                  Load into editor
                </button>
              {/if}
              <button
                type="button"
                class="secondary"
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
  .workflow {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .workflow-header {
    padding: 24px 32px;
    border-bottom: 1px solid #e5e7eb;
  }

  .workflow-header h1 {
    margin: 0 0 4px;
    font-size: 24px;
  }

  .subtitle,
  .help {
    margin: 0;
    color: #6b7280;
    font-size: 14px;
  }

  .workflow-content {
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 24px;
    min-height: 0;
  }

  .panel {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 20px;
    background: #ffffff;
  }

  .toolbar {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
  }

  .path {
    margin: 0;
    font-size: 13px;
    color: #6b7280;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .toolbar-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .toolbar-actions button {
    border: 1px solid #2563eb;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    padding: 8px 12px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
  }

  .toolbar-actions .secondary {
    background: #ffffff;
    color: #2563eb;
  }

  .toolbar-actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .browser {
    display: grid;
    grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
    gap: 24px;
    align-items: start;
  }

  .file-list {
    display: flex;
    flex-direction: column;
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
    border-radius: 8px;
    background: transparent;
    cursor: pointer;
  }

  .file-row:hover {
    background: #f3f4f6;
  }

  .file-row.active {
    background: #eff6ff;
  }

  .file-name {
    font-size: 13px;
    color: #111827;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    word-break: break-all;
  }

  .file-meta {
    font-size: 12px;
    color: #6b7280;
  }

  .badge {
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: 999px;
    background: #dbeafe;
    color: #1d4ed8;
    font-size: 11px;
    font-family: system-ui, sans-serif;
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
    color: #111827;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    word-break: break-all;
  }

  pre {
    margin: 0;
    padding: 16px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
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
    color: #92400e;
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 8px;
    padding: 8px 12px;
  }

  .error {
    margin: 0;
    font-size: 13px;
    color: #dc2626;
  }

  @media (max-width: 1100px) {
    .browser {
      grid-template-columns: 1fr;
    }
  }
</style>
