<script lang="ts">
  /**
   * What the characteristics page produces, as GloBI will read it: the three saved files
   * (to view or download), the model name written into semantic-fields.yaml, and the GIS
   * data with each building's characteristics added as columns.
   */
  import { onMount } from 'svelte';
  import { fetchArtifactStatuses, fetchWorkspaceFileContent } from '../../api/artifacts';
  import { EDITOR_KINDS, dirtyKinds } from '../../stores/projectArtifacts';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { downloadFromResponse, downloadText } from '../../utils/download';
  import Explain from '../Explain.svelte';
  import { HELP } from '../../help';
  const help = HELP.characteristics;

  const LABELS = { 'semantic-fields': 'Characteristics', 'component-map': 'Model parts', priors: 'Estimates' };

  let { reloadKey = 0 }: { /** Bump to re-read the files, e.g. after a save. */ reloadKey?: number } = $props();

  let files = $state<Array<{ kind: (typeof EDITOR_KINDS)[number]; path: string; content: string | null }>>([]);
  let error = $state<string | null>(null);
  let savedGis = $state<string | null>(null);

  onMount(() => {
    void load();
  });

  $effect(() => {
    if (reloadKey) void load();
  });

  async function load() {
    error = null;
    try {
      const statuses = await fetchArtifactStatuses();
      files = await Promise.all(
        EDITOR_KINDS.map(async (kind) => {
          const path = statuses.find((status) => status.kind === kind)?.globiPath ?? '';
          const content = await fetchWorkspaceFileContent(path)
            .then((file) => file.content)
            .catch(() => null);
          return { kind, path, content };
        })
      );
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to read the project files.';
    }
  }

  /** The GIS rows with every "from my data" characteristic applied, downloaded or saved into the project. */
  async function exportGis(save: boolean) {
    error = null;
    try {
      const response = await fetch(`/api/gis/export-enriched${save ? '?save=true' : ''}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || 'Export failed.');
      }
      if (save) savedGis = (await response.json()).path;
      else await downloadFromResponse(response, 'buildings-with-characteristics.geojson');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Export failed.';
    }
  }
</script>

<Explain text={help.files} />

<section class="panel">
  <label class="name">
    <span>Model name <span class="muted">(the Name in semantic-fields.yaml)</span></span>
    <input
      value={$semanticFieldsStore.configName}
      onchange={(event) =>
        semanticFieldsStore.setConfigMeta({ configName: (event.currentTarget as HTMLInputElement).value })}
    />
  </label>
</section>

{#each files as file (file.kind)}
  <section class="panel file">
    <h2>
      {LABELS[file.kind]} <code class="muted">{file.path}</code>
      {#if $dirtyKinds.includes(file.kind)}<span class="unsaved">unsaved changes: Save to update</span>{/if}
      {#if file.content}
        <button
          type="button"
          class="btn btn-secondary btn-sm download"
          onclick={() => downloadText(file.content ?? '', file.path.split('/').pop() ?? file.path, 'application/x-yaml')}
        >
          Download
        </button>
      {/if}
    </h2>
    {#if file.content}
      <pre>{file.content}</pre>
    {:else}
      <p class="muted">Not saved yet.</p>
    {/if}
  </section>
{/each}

<section class="panel">
  <h2>Buildings with their characteristics</h2>
  <p class="muted">
    Your GIS data with a column per characteristic that comes from data. GloBI reads these columns, so the file it
    runs on must have them.
  </p>
  <div class="row">
    <button type="button" class="btn btn-secondary btn-sm" onclick={() => exportGis(false)}>Download GeoJSON</button>
    <button type="button" class="btn btn-secondary btn-sm" onclick={() => exportGis(true)}>Save to project</button>
    {#if savedGis}<span class="muted">Saved to {savedGis}</span>{/if}
  </div>
</section>

{#if error}<p class="error" role="alert">{error}</p>{/if}

<style>
  .name {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
    max-width: 420px;
  }

  h2 {
    display: flex;
    gap: var(--space-2);
    align-items: baseline;
    flex-wrap: wrap;
    margin: 0;
    font-size: var(--text-md);
  }

  .download {
    margin-left: auto;
  }

  pre {
    margin: 0;
    max-height: 360px;
    overflow: auto;
    font-size: 12px;
    background: var(--surface-2);
    padding: var(--space-3);
    border-radius: var(--radius);
  }

  p {
    margin: 0;
    font-size: var(--text-sm);
  }

  .muted {
    color: var(--text-muted);
    font-weight: 400;
  }

  .unsaved {
    font-size: 12px;
    font-weight: 600;
    color: var(--warn-text);
  }

  .row {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
</style>
