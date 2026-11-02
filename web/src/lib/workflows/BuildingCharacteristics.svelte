<script lang="ts">
  /**
   * Building characteristics: one place to define each characteristic's values, how it
   * is known per building, and what it changes in the model. The page holds no data of
   * its own -- it reads the derived `characteristics` view and saves the three GloBI
   * files (semantic fields, component map, priors) together.
   */
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import CharacteristicCard from '../components/characteristics/CharacteristicCard.svelte';
  import AddCharacteristic from '../components/characteristics/AddCharacteristic.svelte';
  import InspectBuilding from '../components/characteristics/InspectBuilding.svelte';
  import GlobiFiles from '../components/characteristics/GlobiFiles.svelte';
  import PartDecisions from '../components/characteristics/PartDecisions.svelte';
  import SamplePreview from '../components/priorTrees/SamplePreview.svelte';
  import Explain from '../components/Explain.svelte';
  import Select from '../components/Select.svelte';
  import Icon from '../components/Icon.svelte';
  import { characteristics } from '../stores/characteristics';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { gisDataset } from '../stores/projectStore';
  import { EDITOR_KINDS, dirtyKinds, loadSavedArtifact, saveDirtyArtifacts, savedAt } from '../stores/projectArtifacts';
  import { formatSavedAt } from '../api/artifacts';
  import type { SemanticField, SemanticFieldTemplateSummary, SemanticFieldsPreview } from '../types/semanticFields';
  import ComponentMapGraph from '../components/componentMap/ComponentMapGraph.svelte';
  import ComponentMapTable from '../components/componentMap/ComponentMapTable.svelte';
  import ComponentSelectorEditor from '../components/componentMap/ComponentSelectorEditor.svelte';
  import PriorTreeGraph from '../components/priorTrees/PriorTreeGraph.svelte';
  import { componentMapStore } from '../stores/componentMapStore';
  import { partRulesStore } from '../stores/partRulesStore';
  import { libraryCheck as libraryCheckStore, navigateTo, runLibraryCheck } from '../stores/projectStore';
  import { priorTreesStore } from '../stores/priorTreesStore';
  import { samplePriorTree, validatePriorTree } from '../api/priorTrees';
  import type { SampleSummary } from '../types/priorTrees';
  import { buildEmptyComponentMap } from '../utils/componentMapTree';
  import { comboBudget, howKnown } from '../utils/characteristics';
  import { HELP } from '../help';
  const help = HELP.characteristics;

  let tab = $state<'characteristics' | 'parts' | 'connections' | 'files'>('characteristics');
  let adding = $state(false);
  let inspecting = $state(false);
  let filesReload = $state(0);
  /** Problems from the last Check, per file; null until Check has run. */
  let checks = $state<{ characteristics: string[]; parts: string[]; estimates: string[]; warnings: string[] } | null>(null);
  let checking = $state(false);
  let fullSample = $state<SampleSummary | null>(null);
  let sampling = $state(false);
  let examples = $state<Array<{ kind: 'semantic-fields' | 'component-map' | 'priors'; name: string; filename: string }>>([]);

  let templates = $state<SemanticFieldTemplateSummary[]>([]);
  let error = $state<string | null>(null);
  let notice = $state<string | null>(null);
  let saving = $state(false);
  let preview = $state<SemanticFieldsPreview | null>(null);
  let previewLoading = $state(false);
  let previewTimer: ReturnType<typeof setTimeout> | null = null;

  const selected = $derived(
    $characteristics.find((view) => view.field.id === $semanticFieldsStore.selectedFieldId) ?? $characteristics[0] ?? null
  );
  const selectedPreview = $derived(
    preview?.field_previews.find((entry) => entry.field_name === selected?.field.name) ?? null
  );
  const apiFields = $derived(semanticFieldsStore.buildApiPayload($semanticFieldsStore).fields);
  const toFinish = $derived($characteristics.filter((view) => view.issues.length > 0).length);
  const fieldOrder = $derived($characteristics.map((view) => view.field.name));
  const budget = $derived(comboBudget($componentMapStore.map, $semanticFieldsStore.fields, $priorTreesStore.config));
  /** With part rules, parts are decided on Component Map and the map here is their compiled output. */
  const hasRules = $derived(Boolean($partRulesStore.rules));
  const libraryCheck = $derived($libraryCheckStore);

  /** The overview needs a map to draw, and the estimate order comes from validation. */
  async function showConnections(path: string | null = null) {
    tab = 'connections';
    if (!$componentMapStore.map) componentMapStore.setMap(buildEmptyComponentMap());
    if (path) componentMapStore.setSelectedPath(path);
    try {
      const estimated = $semanticFieldsStore.fields.filter((field) => howKnown(field) === 'estimate');
      const result = await validatePriorTree($priorTreesStore.config, estimated.map((field) => field.name));
      priorTreesStore.setDependencies(result.dependencies ?? { nodes: [], edges: [] });
    } catch {
      // The order graph is a nicety; the rest of the overview works without it.
    }
  }

  const DIRTY_LABELS = { 'semantic-fields': 'characteristics', 'component-map': 'component map', priors: 'estimates', 'part-rules': 'component map' };
  const hasSaved = $derived(EDITOR_KINDS.some((kind) => $savedAt[kind]));

  onMount(() => {
    void loadTemplates();
    void loadExamples();
    const warn = (event: BeforeUnloadEvent) => {
      if ($dirtyKinds.length > 0) event.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  });

  const selectedId = $derived(selected?.field.id);
  // Refresh the preview whenever a different characteristic is opened.
  $effect(() => {
    if (selectedId) schedulePreview();
  });

  async function loadTemplates() {
    try {
      const response = await fetch('/api/semantic-fields/templates');
      templates = (await response.json()).templates || [];
    } catch {
      error = 'Failed to load examples.';
    }
  }

  async function loadTemplate(filename: string) {
    if ($semanticFieldsStore.fields.length > 0 && !confirm('This replaces your characteristics. Continue?')) return;
    try {
      const response = await fetch(`/api/semantic-fields/templates/${filename}`);
      semanticFieldsStore.loadFromTemplate(await response.json());
    } catch {
      error = 'Failed to load the example.';
    }
  }

  /** Walk the list in order to the next characteristic that still has something to fix. */
  function nextToFinish() {
    const views = $characteristics;
    const start = views.findIndex((view) => view.field.id === selected?.field.id);
    const next = [...views.slice(start + 1), ...views.slice(0, start + 1)].find((view) => view.issues.length > 0);
    if (next) semanticFieldsStore.setSelectedField(next.field.id);
  }

  function updateField(next: SemanticField) {
    semanticFieldsStore.updateField(next.id, next);
    schedulePreview();
  }

  function schedulePreview() {
    if (!$gisDataset?.validated) return;
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 300);
  }

  async function refreshPreview() {
    previewLoading = true;
    try {
      const response = await fetch('/api/semantic-fields/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
      });
      preview = response.ok ? await response.json() : null;
    } catch {
      preview = null;
    } finally {
      previewLoading = false;
    }
  }

  const EXAMPLE_KINDS = [
    { kind: 'semantic-fields', label: 'Characteristics', url: '/api/semantic-fields/templates' },
    { kind: 'component-map', label: 'Component map', url: '/api/component-map/templates' },
    { kind: 'priors', label: 'Estimates', url: '/api/prior-trees/templates' },
  ] as const;

  async function loadExamples() {
    const lists = await Promise.all(
      EXAMPLE_KINDS.map(async ({ kind, url }) => {
        const response = await fetch(url).catch(() => null);
        const data = response?.ok ? await response.json() : { templates: [] };
        return (data.templates as SemanticFieldTemplateSummary[]).map((t) => ({ kind, name: t.name, filename: t.filename }));
      })
    );
    examples = lists.flat();
  }

  /** Replace one of the three files' contents with an example's. */
  async function loadExample(value: string) {
    const example = examples.find((entry) => `${entry.kind}/${entry.filename}` === value);
    if (!example) return;
    const label = EXAMPLE_KINDS.find((entry) => entry.kind === example.kind)?.label.toLowerCase();
    if (!confirm(`Replace your ${label} with the "${example.name}" example?`)) return;
    error = null;
    try {
      const url = EXAMPLE_KINDS.find((entry) => entry.kind === example.kind)!.url;
      const data = await (await fetch(`${url}/${example.filename}`)).json();
      if (example.kind === 'semantic-fields') semanticFieldsStore.loadFromTemplate(data);
      else if (example.kind === 'component-map') componentMapStore.loadFromTemplate(data, example.filename);
      else priorTreesStore.loadFromTemplate(data, example.filename);
      checks = null;
    } catch {
      error = 'Failed to load the example.';
    }
  }

  /** Run the server's checks on all three files and keep the results for the readiness marks. */
  async function runChecks() {
    checking = true;
    error = null;
    try {
      const post = (url: string, body: unknown) =>
        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(
          (response) => response.json()
        );
      const fields = $semanticFieldsStore.fields;
      const [semantic, map, priors] = await Promise.all([
        post('/api/semantic-fields/validate', semanticFieldsStore.buildApiPayload($semanticFieldsStore)),
        post('/api/component-map/validate', {
          component_map: $componentMapStore.map ?? {},
          semantic_fields: fields.map((field) => ({ name: field.name, options: field.options })),
        }),
        validatePriorTree(
          $priorTreesStore.config,
          fields.filter((field) => howKnown(field) === 'estimate').map((field) => field.name)
        ),
      ]);
      componentMapStore.setValidation(map.valid, map.errors || [], map.generated_names || []);
      priorTreesStore.setValidation(priors);
      checks = {
        characteristics: [
          ...(semantic.errors ?? []),
          ...$characteristics.flatMap((view) => view.issues.map((issue) => `${view.field.name || 'Untitled'}: ${issue}`)),
        ],
        parts: map.errors ?? [],
        estimates: priors.errors ?? [],
        warnings: priors.warnings ?? [],
      };
    } catch (e) {
      error = e instanceof Error ? e.message : 'Check failed.';
    } finally {
      checking = false;
    }
  }

  /** Save, then resolve every combination the buildings have against the component library. */
  async function checkLibrary() {
    await save();
    if (error) return;
    checking = true;
    await runLibraryCheck();
    checking = false;
  }

  async function previewAllEstimates() {
    sampling = true;
    error = null;
    try {
      fullSample = await samplePriorTree($semanticFieldsStore.fields, $priorTreesStore.config, 2000, 0);
    } catch (e) {
      fullSample = null;
      error = e instanceof Error ? e.message : 'Failed to sample.';
    } finally {
      sampling = false;
    }
  }

  async function save() {
    saving = true;
    error = null;
    notice = null;
    try {
      const saved = await saveDirtyArtifacts();
      filesReload += 1;
      notice = saved.length ? `Saved ${saved.length} file${saved.length === 1 ? '' : 's'}.` : 'Nothing to save.';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Save failed.';
    } finally {
      saving = false;
    }
  }

  async function revert() {
    if (!confirm('Discard unsaved changes and reload the saved files?')) return;
    error = null;
    try {
      for (const kind of EDITOR_KINDS) if ($savedAt[kind]) await loadSavedArtifact(kind);
      notice = 'Reloaded the saved files.';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to reload.';
    }
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Building characteristics <span class="globi">(GloBI: semantic fields)</span> <Explain text={help.page} tip /></h1>
    <Explain text={help.page} />
    {#if !hasRules && (budget.records > 0 || budget.estimateRows > 0)}
      <p class="budget" title={help.budget}>
        Needs {budget.records.toLocaleString()} library record{budget.records === 1 ? '' : 's'} ·
        {budget.estimateRows.toLocaleString()} estimate row{budget.estimateRows === 1 ? '' : 's'}
      </p>
    {/if}
  </div>

  <div class="workflow-content">
    {#if !$gisDataset?.validated}
      <WorkflowGuide
        title="No validated GIS data yet"
        message="Characteristics from your data are computed from the cleaned GIS columns. You can still type a characteristic's values now and bind it to a column later."
        actionLabel="Go to GIS Cleaning"
        actionWorkflow="gis-cleaning"
      />
    {/if}

    {#if $characteristics.length === 0}
      <div class="panel empty-start">
        <h2>Start a new region</h2>
        <p class="hint">
          Describe the few things that set your buildings apart. Start with what your data records, then add what you
          need to estimate; each one opens to finish once added.
        </p>
        <AddCharacteristic onAdded={() => {}} />
        {#if templates.length > 0}
          <p class="hint actions">
            Or start from an example:
            {#each templates as template}
              <button type="button" class="btn btn-link" title={template.description} onclick={() => loadTemplate(template.filename)}>
                {template.name}
              </button>
            {/each}
          </p>
        {/if}
      </div>
    {:else}
      <div class="tab-bar">
      <div class="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'characteristics'} class:active={tab === 'characteristics'} onclick={() => (tab = 'characteristics')}>
          Characteristics
        </button>
        {#if hasRules}
          <button type="button" role="tab" aria-selected="false" onclick={() => navigateTo('model-parts')}>
            Component map <Icon name="arrow-right" size={14} />
          </button>
        {:else}
          <button type="button" role="tab" aria-selected={tab === 'parts'} class:active={tab === 'parts'} onclick={() => (tab = 'parts')}>
            What decides each part?
          </button>
        {/if}
        <button type="button" role="tab" aria-selected={tab === 'connections'} class:active={tab === 'connections'} onclick={() => showConnections()}>
          {#if hasRules}Advanced: component-map.yaml{:else}All connections <span class="globi">(component map)</span>{/if}
        </button>
        <button type="button" role="tab" aria-selected={tab === 'files'} class:active={tab === 'files'} onclick={() => (tab = 'files')}>
          GloBI files
        </button>
      </div>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          disabled={!$gisDataset?.validated}
          title={$gisDataset?.validated ? help.inspect : 'Validate GIS data first'}
          onclick={() => (inspecting = !inspecting)}
        >
          Inspect a building
        </button>
      </div>

      {#if inspecting}
        <InspectBuilding onClose={() => (inspecting = false)} />
      {/if}

      {#if tab === 'connections'}
        <Explain text={help.connections} />
        <div class="connections">
          <section class="panel">
            <div class="segmented">
              <button type="button" aria-pressed={$componentMapStore.viewMode === 'graph'} onclick={() => componentMapStore.setViewMode('graph')}>Graph</button>
              <button type="button" aria-pressed={$componentMapStore.viewMode === 'table'} onclick={() => componentMapStore.setViewMode('table')}>Table</button>
            </div>
            {#if $componentMapStore.map}
              {#if $componentMapStore.viewMode === 'graph'}
                <ComponentMapGraph />
              {:else}
                <ComponentMapTable />
              {/if}
            {/if}
          </section>
          <aside class="panel">
            {#if hasRules}
              <p class="hint">This map is compiled from your part rules, so it is read-only here. Change what decides each part on <button type="button" class="btn btn-link" onclick={() => navigateTo('model-parts')}>Component Map</button>.</p>
            {:else if $componentMapStore.selectedPath}
              <ComponentSelectorEditor path={$componentMapStore.selectedPath} />
            {:else}
              <p class="hint">Pick a model part in the graph or table to see which characteristics choose it.</p>
            {/if}
          </aside>
        </div>
        {#if $priorTreesStore.dependencies.nodes.length > 0}
          <div class="panel">
            <h2>Estimate order <Explain text={HELP.priorTrees.order} tip /></h2>
            <PriorTreeGraph graph={$priorTreesStore.dependencies} />
          </div>
        {/if}
        {#if $priorTreesStore.config.joints.length > 0 || Object.keys($priorTreesStore.config.priors).length > 0}
          <div class="panel">
            <h2>All estimates over your buildings <Explain text={HELP.priorTrees.preview} tip /></h2>
            <div class="actions">
              <button type="button" class="btn btn-secondary btn-sm" onclick={previewAllEstimates} disabled={sampling}>
                {sampling ? 'Drawing…' : 'Preview 2,000 draws'}
              </button>
            </div>
            {#if fullSample}<SamplePreview sample={fullSample} />{/if}
          </div>
        {/if}
      {:else if tab === 'parts'}
        <PartDecisions {fieldOrder} />
      {:else if tab === 'files'}
        <GlobiFiles reloadKey={filesReload} />
      {:else}
      <div class="layout">
        <aside class="list">
          <div class="list-header">
            <h2>Characteristics <Explain text={help.list} tip /></h2>
            <button type="button" class="btn btn-sm" onclick={() => (adding = true)} data-tour="char-add"><Icon name="plus" size={14} />Add</button>
          </div>
          {#if toFinish > 0}
            <button type="button" class="btn btn-secondary btn-sm next" onclick={nextToFinish}>
              Next to finish ({toFinish}) <Icon name="arrow-right" size={14} />
            </button>
          {/if}
          {#each $characteristics as view (view.field.id)}
            <button
              type="button"
              class="item"
              class:active={view.field.id === selected?.field.id}
              onclick={() => {
                adding = false;
                semanticFieldsStore.setSelectedField(view.field.id);
              }}
            >
              <strong>{view.field.name || 'Untitled'}</strong>
              <span class="meta">
                <span class="tag {view.howKnown}">{view.howKnown === 'data' ? 'from data' : 'estimated'}</span>
                {#if view.issues.length > 0}
                  <span class="tag tag-err" title={view.issues.join('\n')}>
                    {view.issues.length} to fix
                  </span>
                {/if}
              </span>
            </button>
          {/each}
          <Explain text={help.list} />
        </aside>

        {#if adding}
          <div class="panel">
            <AddCharacteristic onAdded={() => (adding = false)} onCancel={() => (adding = false)} />
          </div>
        {:else if selected}
          {#key selected.field.id}
            <CharacteristicCard
              view={selected}
              gisColumns={$semanticFieldsStore.gisColumns}
              {apiFields}
              preview={selectedPreview}
              {previewLoading}
              onFieldChange={updateField}
              {fieldOrder}
              onShowConnections={(path) => showConnections(path)}
            />
          {/key}
        {/if}
      </div>
      {/if}
    {/if}

    <div class="actions">
      <button type="button" class="btn" onclick={save} disabled={saving || $dirtyKinds.length === 0} title={help.save} data-tour="char-save">
        {saving ? 'Saving…' : 'Save'}
      </button>
      {#if hasSaved}
        <button type="button" class="btn btn-secondary" onclick={revert}>Revert</button>
      {/if}
      <button type="button" class="btn btn-secondary" onclick={runChecks} disabled={checking} title={help.check}>
        {checking ? 'Checking…' : 'Check'}
      </button>
      <button
        type="button"
        class="btn btn-secondary"
        onclick={checkLibrary}
        disabled={checking || saving || !$componentMapStore.map}
        title="Saves, then checks that every combination your buildings have finds its records in the component library"
      >
        Save &amp; check library
      </button>
      {#if examples.length > 0}
        <div class="examples-select">
          <Select
            value=""
            options={examples.map((example) => ({
              value: `${example.kind}/${example.filename}`,
              label: example.name,
              group: EXAMPLE_KINDS.find((entry) => entry.kind === example.kind)?.label,
            }))}
            placeholder="Load an example…"
            ariaLabel="Load an example"
            onChange={(value) => void loadExample(value)}
          />
        </div>
      {/if}
      <span class="hint">
        {#if $dirtyKinds.length > 0}
          Unsaved changes: {$dirtyKinds.map((kind) => DIRTY_LABELS[kind]).join(', ')}
        {:else}
          {formatSavedAt($savedAt['semantic-fields'])}
        {/if}
      </span>
    </div>

    {#if libraryCheck}
      {#if libraryCheck.ok}
        <p class="status-ok">
          <Icon name="check" size={14} />Library check passed: {libraryCheck.buildings
            ? `all ${libraryCheck.buildings.toLocaleString()} buildings`
            : 'every combination of values'} resolve.
        </p>
      {:else}
        <p class="status-err"><Icon name="x" size={14} />Library check: {libraryCheck.errors[0] ?? 'it does not resolve.'}</p>
      {/if}
    {/if}

    {#if checks}
      {@const sections = [
        { label: 'Characteristics', items: checks.characteristics },
        { label: 'Component map', items: checks.parts },
        { label: 'Estimates', items: checks.estimates },
      ].filter((section) => section.items.length > 0)}
      <div class="check-results {sections.length > 0 ? 'callout callout-err' : 'panel'}">
        {#if sections.length === 0}
          <p class="status-ok"><Icon name="check" size={14} />All checks pass.</p>
        {:else}
          {#each sections as section}
            <h3>{section.label}</h3>
            <ul>
              {#each section.items as item}<li>{item}</li>{/each}
            </ul>
          {/each}
        {/if}
        {#if checks.warnings.length > 0}
          <h3>Worth checking</h3>
          <ul>
            {#each checks.warnings as warning}<li>{warning}</li>{/each}
          </ul>
        {/if}
      </div>
    {/if}

    {#if notice}<p class="hint">{notice}</p>{/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </div>
</section>

<style>
  .globi {
    font-weight: 300;
    font-size: var(--text-md);
    color: var(--text-muted);
  }

  .budget {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-2);
  }

  /* Inspect sits outside the tablist but on the same rule. */
  .tab-bar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    border-bottom: 1px solid var(--border);
  }

  .tab-bar .tabs {
    flex: 1;
    align-self: stretch;
    border-bottom: none;
  }

  .connections {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
    gap: var(--space-4);
  }

  .connections .panel {
    min-height: 520px;
  }

  .connections .segmented {
    align-self: flex-start;
  }

  .next {
    width: 100%;
    margin-bottom: var(--space-3);
  }

  .examples-select {
    min-width: 200px;
  }

  .check-results {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .check-results h3 {
    margin: 0;
    font-size: var(--text-md);
  }

  .check-results ul {
    margin: 0;
    padding-left: var(--space-5);
    font-size: var(--text-sm);
  }

  .empty-start {
    align-items: flex-start;
  }

  .layout {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }

  .list {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-4);
    background: var(--surface);
  }

  .list-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
  }

  .list-header h2 {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: 600;
  }

  /* Rows inside the framed list: no box of their own, a grey pill when open. */
  .item {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    padding: var(--space-2) var(--space-3);
    margin-bottom: 2px;
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }

  .item:hover {
    background: var(--surface-2);
  }

  .item strong {
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .item.active {
    background: var(--surface-3);
  }

  .meta {
    display: flex;
    gap: var(--space-1);
    flex-wrap: wrap;
  }

  .tag.data {
    background: var(--accent-soft);
    color: var(--accent-hover);
  }

  .tag.estimate {
    background: color-mix(in srgb, var(--series-5) 18%, var(--surface));
    color: var(--text);
  }

  @media (max-width: 900px) {
    .connections,
    .layout {
      grid-template-columns: 1fr;
    }
  }
</style>
