<script lang="ts">
  /**
   * Component map: which library component each part of the model uses, and what makes that
   * differ between buildings. Every part starts on the library's archetype, so the model runs
   * from the start. Parts are cards (one swatch per component in use); clicking one opens its
   * editor in a side panel. Saving compiles the rules into component-map.yaml and the records
   * globi looks up (server/services/part_rules.py).
   */
  import { onMount } from 'svelte';
  import PartRuleEditor from '../components/modelParts/PartRuleEditor.svelte';
  import SidePanel from '../components/SidePanel.svelte';
  import Explain from '../components/Explain.svelte';
  import Icon from '../components/Icon.svelte';
  import { fetchParts, type PartInfo } from '../api/partRules';
  import { fetchComponentRecords, type ComponentRecord } from '../api/componentLibrary';
  import { partRulesStore } from '../stores/partRulesStore';
  import { libraryCheck, navigateTo, runLibraryCheck } from '../stores/projectStore';
  import { dirtyKinds, saveDirtyArtifacts } from '../stores/projectArtifacts';
  import { partStatus, usedOptions, type PartRule } from '../utils/partRules';
  import { partGroup, partLabel, walkOrder } from '../utils/modelParts';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { HELP } from '../help';
  const help = HELP.componentMap;

  const GROUPS = [
    { id: 'Envelope', label: 'Envelope' },
    { id: 'Systems', label: 'Systems' },
    { id: 'Use', label: 'Use' },
  ] as const;

  let parts = $state<PartInfo[]>([]);
  let open = $state<string | null>(null);
  let records = $state<Record<string, ComponentRecord[]>>({});
  let conductivity = $state<Record<string, number>>({});
  let busy = $state(false);
  let error = $state<string | null>(null);
  let showProblems = $state(false);

  const rules = $derived($partRulesStore.rules);
  const ordered = $derived(walkOrder(parts.map((part) => part.path)));
  const typeOf = $derived(Object.fromEntries(parts.map((part) => [part.path, part.type])));
  const status = $derived(Object.fromEntries(ordered.map((path) => [path, partStatus(rules?.parts[path])])));
  const count = (value: string) => Object.values(status).filter((s) => s === value).length;
  const options = $derived(Object.fromEntries($semanticFieldsStore.fields.map((field) => [field.name, field.options])));

  onMount(async () => {
    parts = await fetchParts();
    if (!$libraryCheck) void runLibraryCheck();
  });

  /** One colour per component a part uses, in the same order its editor shows them. */
  function swatches(rule: PartRule | undefined): string[] {
    return rule ? usedOptions(rule, options).map((_, i) => `var(--series-${(i % 8) + 1})`) : [];
  }

  async function loadRecords(type: string) {
    try {
      records = { ...records, [type]: await fetchComponentRecords(type) };
      if (type === 'ConstructionAssembly' && Object.keys(conductivity).length === 0) {
        const materials = await fetchComponentRecords('ConstructionMaterial');
        conductivity = Object.fromEntries(materials.map((m) => [m.Name, Number(m.Conductivity)]));
      }
    } catch {
      records = { ...records, [type]: [] };
    }
  }

  function openPart(path: string | null) {
    open = path;
    if (path && !records[typeOf[path]]) void loadRecords(typeOf[path]);
  }

  /** The next part in walk order (biggest energy effect first) that is still a default. */
  function nextAfter(path: string): string | null {
    const start = ordered.indexOf(path);
    return [...ordered.slice(start + 1), ...ordered.slice(0, start)].find((p) => status[p] === 'todo' || status[p] === 'assumed') ?? null;
  }

  async function save() {
    busy = true;
    error = null;
    try {
      await saveDirtyArtifacts();
      const compile = $partRulesStore.compile;
      if (compile && !compile.ok) error = compile.errors.join(' ');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Save failed.';
    } finally {
      busy = false;
    }
  }

  function change(path: string, rule: PartRule) {
    partRulesStore.setPart(path, rule);
  }
</script>

<div class="workflow">
  <header class="workflow-header">
    <div class="title-row">
      <h1>Component map <Explain text={help.page} tip /></h1>
      <div class="status-row">
        {#if rules}
        <span class="count" title="Parts that differ between buildings"><span class="swatch filled"></span>{count('varies')} vary</span>
        <span class="count" title="Parts nobody has decided yet: they use the archetype's component"><span class="swatch hollow"></span>{count('assumed')} default</span>
        {#if count('todo')}<span class="count bad" title="Parts without a component"><Icon name="alert" size={14} />{count('todo')} missing</span>{/if}
        {/if}
        {#if $libraryCheck}
          <button type="button" class="run" data-tour="map-status" class:ok={$libraryCheck.ok} class:bad={!$libraryCheck.ok} aria-expanded={showProblems} onclick={() => (showProblems = !showProblems)}>
            <Icon name={$libraryCheck.ok ? 'check' : 'x'} size={14} />
            {$libraryCheck.ok ? ($libraryCheck.buildings ? `${$libraryCheck.buildings.toLocaleString()} buildings run` : 'runs') : "doesn't run"}
          </button>
        {/if}
        <button type="button" class="btn btn-secondary btn-sm" onclick={() => runLibraryCheck()} disabled={busy} title="Resolve every building against the library" data-tour="map-check">Check</button>
        <button type="button" class="btn btn-sm" onclick={save} disabled={busy || $dirtyKinds.length === 0} data-tour="map-save">{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
    <Explain text={help.page} />
    {#if showProblems && $libraryCheck && !$libraryCheck.ok}
      <ul class="problems">{#each $libraryCheck.errors as message}<li>{message}</li>{/each}</ul>
    {/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </header>

  <div class="body" class:panel-open={open !== null}>
    <div class="cards-area" data-tour="map-cards">
      {#if !rules && $partRulesStore.converting}
        <p class="hint">Reading this project's components…</p>
      {:else if !rules}
        <p class="hint">Couldn't read this project's component map. Check the library in Component Library, then reopen the project.</p>
      {:else}
        {#if count('varies') === 0}
          <div class="start">
            <span class="swatch hollow big"></span>
            <span>Every building uses the same components. Click a part to make it vary.</span>
            <button type="button" class="btn btn-link" onclick={() => navigateTo('gis-cleaning')}><Icon name="file" size={14} />Load buildings data</button>
          </div>
          <Explain text={help.start} />
        {/if}
        {#each GROUPS as group}
          <section class="group">
            <h2>{group.label}</h2>
            <div class="cards">
              {#each ordered.filter((path) => partGroup(path) === group.id) as path (path)}
                {@const rule = rules.parts[path]}
                <button type="button" class="card {status[path]}" class:selected={open === path} aria-pressed={open === path} onclick={() => openPart(open === path ? null : path)}>
                  <span class="name">{partLabel(path)}</span>
                  <span class="swatches">
                    {#if status[path] === 'todo'}
                      <Icon name="alert" size={14} />
                    {:else if status[path] === 'assumed'}
                      <span class="swatch hollow"></span>
                    {:else}
                      {#each swatches(rule).slice(0, 8) as colour}<span class="swatch" style:background={colour}></span>{/each}
                    {/if}
                  </span>
                  {#if rule?.depends_on.length}<span class="by">{rule.depends_on.join(' × ')}</span>{/if}
                </button>
              {/each}
            </div>
          </section>
        {/each}
      {/if}
    </div>

    {#if open && rules}
      <div class="editor-slot">
        <SidePanel title={partLabel(open)} subtitle={typeOf[open]} onClose={() => (open = null)}>
          {#key open}
            <PartRuleEditor
              type={typeOf[open]}
              path={open}
              label={partLabel(open)}
              rule={rules.parts[open]}
              records={records[typeOf[open]] ?? null}
              {conductivity}
              onChange={(rule) => change(open as string, rule)}
              onRecordsChanged={() => loadRecords(typeOf[open as string])}
              onNext={nextAfter(open) ? () => openPart(nextAfter(open as string)) : null}
            />
          {/key}
        </SidePanel>
      </div>
    {/if}
  </div>
</div>

<style>
  .workflow { height: 100%; display: flex; flex-direction: column; min-height: 0; }
  .title-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
  .status-row { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; font-size: var(--text-sm); color: var(--text-2); }
  .count { display: inline-flex; align-items: center; gap: 6px; }
  .run { display: inline-flex; align-items: center; gap: 4px; border: 1px solid; border-radius: 999px; padding: 1px 10px; font-size: var(--text-sm); cursor: pointer; background: none; }
  .run.ok { color: var(--ok-text); border-color: var(--ok-border); background: var(--ok-bg); }
  .run.bad, .count.bad { color: var(--err-text); }
  .run.bad { border-color: var(--err-border); background: var(--err-bg); }
  .problems { margin: var(--space-2) 0 0; padding-left: 20px; font-size: var(--text-sm); color: var(--err-text); }
  .body { position: relative; flex: 1; display: grid; grid-template-columns: minmax(0, 1fr); min-height: 0; overflow: hidden; }
  .body.panel-open { grid-template-columns: minmax(0, 1fr) minmax(400px, 520px); }
  .cards-area { overflow: auto; padding: var(--space-4) var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
  .editor-slot { min-height: 0; overflow: hidden; }
  .start { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; font-size: var(--text-sm); color: var(--text-2); }
  .group h2 { margin: 0 0 var(--space-2); font-size: var(--text-md); }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-2); }
  .card { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-height: 76px; padding: var(--space-2) var(--space-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--text); text-align: left; cursor: pointer; }
  .card:hover { border-color: var(--border-strong); }
  .card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
  .card.todo { border-color: var(--err-border); color: var(--err-text); }
  .name { font-size: var(--text-sm); font-weight: 600; }
  .swatches { display: flex; gap: 3px; flex-wrap: wrap; min-height: 14px; }
  .by { font-size: var(--text-xs); color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .swatch { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
  .swatch.filled { background: var(--series-1); }
  .swatch.hollow { border: 1.5px dashed var(--text-muted); }
  .swatch.big { width: 18px; height: 18px; }
  @media (max-width: 1100px) {
    .body.panel-open { grid-template-columns: minmax(0, 1fr); }
    .editor-slot { position: absolute; top: 0; right: 0; bottom: 0; width: min(520px, 100%); box-shadow: var(--shadow-lg); z-index: 5; }
  }
</style>
