<script lang="ts">
  /**
   * "What decides each part?": the component map from the model part's side, in plain words
   * ("Lighting depends on Typology and Age"). Each toggle writes the same selectors as a
   * characteristic card's checkboxes (setPartForField), and each row shows the library records
   * that choice calls for and how many exist.
   */
  import { untrack } from 'svelte';
  import { componentMapStore } from '../../stores/componentMapStore';
  import { componentTreeStore } from '../../stores/componentTreeStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { navigateTo } from '../../stores/projectStore';
  import { checkComponentExistence } from '../../api/componentLibrary';
  import { MODEL_PARTS, defaultSuffix, otherPaths, type ModelPart } from '../../utils/modelParts';
  import {
    buildEmptyComponentMap,
    buildSelectorCombinations,
    fieldStatusAtPath,
    getSelectorAtPath,
    setPartForField,
  } from '../../utils/componentMapTree';

  let { fieldOrder }: { /** Characteristic names in list order. */ fieldOrder: string[] } = $props();

  const GROUPS = [
    { id: 'Envelope', label: 'Envelope' },
    { id: 'Systems', label: 'Systems' },
    { id: 'Use', label: 'How the building is used' },
  ] as const;

  /** Whole groups get one record for everything under them. */
  const GROUP_LABELS: Record<string, string> = {
    Envelope: 'Whole envelope',
    'Envelope.Assemblies': 'All constructions',
    Operations: 'All operations',
    'Operations.SpaceUse': 'Whole space use (all loads)',
    'Operations.HVAC': 'Whole HVAC',
    'Operations.HVAC.ConditioningSystems': 'Heating and cooling together',
  };

  const map = $derived($componentMapStore.map);
  const nodes = $derived($componentTreeStore.nodesByPath);
  const fields = $derived($semanticFieldsStore.fields.map((field) => ({ name: field.name, options: field.options })));

  function plainLabel(path: string): string {
    if (GROUP_LABELS[path]) return GROUP_LABELS[path];
    const segments = path.split('.');
    const last = segments[segments.length - 1];
    if (last === 'Schedule' && segments.length > 1) return `${segments[segments.length - 2]} schedule`;
    return nodes[path]?.displayName ?? last;
  }

  const groupParts = $derived(
    otherPaths(Object.keys(nodes))
      .filter((path) => nodes[path]?.componentType)
      .map((path): ModelPart => ({ id: path, label: plainLabel(path), group: 'Envelope', paths: [path] }))
  );
  const allLabels = $derived(
    Object.fromEntries([...MODEL_PARTS, ...groupParts].flatMap((part) => part.paths.map((path) => [path, part.label])))
  );

  /** Which characteristics decide this part, and whether that is its own choice or a parent group's. */
  function decision(part: ModelPart) {
    const paths = part.paths.filter((path) => nodes[path]);
    const own = map ? paths.map((path) => getSelectorAtPath(map, path)).find(Boolean) : null;
    const fromField = (name: string) => (map ? fieldStatusAtPath(map, paths[0] ?? '', name) : { status: 'off' as const });
    const inheritedFrom = !own && paths[0] ? fieldOrder.map(fromField).find((s) => s.status === 'inherited')?.from : undefined;
    return { paths, own, inheritedFrom, statusOf: fromField };
  }

  function toggle(part: ModelPart, name: string, on: boolean) {
    const base = map ?? buildEmptyComponentMap();
    const paths = part.paths.filter((path) => nodes[path]);
    const renames = paths.some((path) => {
      const selector = map ? getSelectorAtPath(map, path) : null;
      return selector && (on ? !selector.source_fields.includes(name) : selector.source_fields.length > 1);
    });
    if (renames && !confirm(`This changes the record names for ${part.label}, so records already made for it will no longer be used. Continue?`)) {
      return;
    }
    const next = paths.reduce((current, path) => {
      const status = fieldStatusAtPath(current, path, name).status;
      if (on && status === 'off') return setPartForField(current, path, name, true, fieldOrder, defaultSuffix(path, nodes));
      if (!on && status === 'own') return setPartForField(current, path, name, false, fieldOrder);
      return current;
    }, base);
    componentMapStore.setMap(next);
  }

  function andList(names: string[]): string {
    return names.length <= 1 ? (names[0] ?? '') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
  }

  /** Record names each decided path calls for, by library type. */
  const needed = $derived.by(() => {
    const byPath: Record<string, { type: string; names: string[] }> = {};
    if (!map) return byPath;
    for (const part of [...MODEL_PARTS, ...groupParts]) {
      for (const path of part.paths) {
        const selector = getSelectorAtPath(map, path);
        const type = nodes[path]?.componentType;
        if (!selector || !type) continue;
        byPath[path] = { type, names: buildSelectorCombinations(selector.source_fields, fields, selector.suffix).map((c) => c.name) };
      }
    }
    return byPath;
  });

  let existence = $state<Record<string, Record<string, boolean>>>({});
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const snapshot = needed;
    clearTimeout(timer);
    timer = setTimeout(() => untrack(() => refreshExistence(snapshot)), 400);
  });

  async function refreshExistence(byPath: Record<string, { type: string; names: string[] }>) {
    const namesByType = new Map<string, Set<string>>();
    for (const { type, names } of Object.values(byPath)) {
      const set = namesByType.get(type) ?? new Set<string>();
      names.forEach((name) => set.add(name));
      namesByType.set(type, set);
    }
    try {
      const entries = await Promise.all(
        [...namesByType].map(async ([type, names]) => [type, await checkComponentExistence(type, [...names])] as const)
      );
      existence = Object.fromEntries(entries);
    } catch {
      existence = {};
    }
  }

  function coverage(paths: string[]) {
    const rows = paths.map((path) => needed[path]).filter(Boolean);
    const total = rows.reduce((sum, row) => sum + row.names.length, 0);
    const exist = rows.reduce((sum, row) => sum + row.names.filter((name) => existence[row.type]?.[name]).length, 0);
    return { total, exist };
  }

  function pattern(path: string): string {
    const selector = map ? getSelectorAtPath(map, path) : null;
    if (!selector) return '';
    return [...selector.source_fields.map((name) => `‹${name}›`), ...(selector.suffix ? [selector.suffix] : [])].join('_');
  }
</script>

{#snippet row(part: ModelPart)}
  {@const d = decision(part)}
  {#if d.paths.length > 0}
    {@const cov = coverage(d.paths)}
    <li class="row">
      <div class="what">
        <strong>{part.label}</strong>
        <span class="type">{nodes[d.paths[0]]?.componentType ?? ''}</span>
      </div>
      <div class="chips" role="group" aria-label={`Characteristics that decide ${part.label}`}>
        {#each fieldOrder as name (name)}
          {@const status = d.statusOf(name).status}
          <button
            type="button"
            class="chip"
            class:on={status === 'own'}
            class:inherited={status === 'inherited'}
            aria-pressed={status !== 'off'}
            disabled={status === 'inherited'}
            title={status === 'inherited' ? `Decided with ${allLabels[d.inheritedFrom ?? ''] ?? d.inheritedFrom}; change it there` : ''}
            onclick={() => toggle(part, name, status === 'off')}
          >
            {name}
          </button>
        {:else}
          <span class="muted">Add characteristics first.</span>
        {/each}
      </div>
      <p class="sentence">
        {#if d.own}
          {part.label} depends on <strong>{andList(d.own.source_fields)}</strong>
          → {cov.total} record{cov.total === 1 ? '' : 's'} named <code>{pattern(d.paths[0])}</code>
          · <span class:ok={cov.exist === cov.total} class:missing={cov.exist < cov.total}>{cov.exist} of {cov.total} exist</span>
        {:else if d.inheritedFrom}
          Chosen as part of {allLabels[d.inheritedFrom] ?? d.inheritedFrom}.
        {:else}
          <span class="muted">Not decided by any characteristic.</span>
        {/if}
      </p>
    </li>
  {/if}
{/snippet}

<div class="decisions">
  <p class="intro">
    For each part of the energy model, pick the characteristics that change it, e.g. "Lighting depends on
    Typology and Age". The app writes the component map from these choices; each line shows the library
    records it calls for.
    <button type="button" class="btn btn-link" onclick={() => navigateTo('component-library')}>Build them in Component Library</button>
  </p>
  {#each GROUPS as group}
    <h3>{group.label}</h3>
    <ul>
      {#each MODEL_PARTS.filter((part) => part.group === group.id) as part (part.id)}{@render row(part)}{/each}
    </ul>
  {/each}
  <h3>Schedules and whole groups</h3>
  <p class="muted">A whole group uses one record for everything under it (e.g. one SpaceUse with all its loads).</p>
  <ul>
    {#each groupParts as part (part.id)}{@render row(part)}{/each}
  </ul>
</div>

<style>
  .decisions { display: flex; flex-direction: column; gap: 6px; }
  .intro { margin: 0 0 8px; font-size: 14px; color: var(--text-2); }
  h3 { margin: 14px 0 4px; font-size: 14px; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .row { display: grid; grid-template-columns: minmax(170px, 0.8fr) minmax(0, 2fr); gap: 4px 14px; padding: 8px 0; border-bottom: 1px solid var(--border); }
  .what { display: flex; flex-direction: column; }
  .type { font-size: 11px; color: var(--text-muted); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chip { border: 1px solid var(--border-strong); background: var(--surface); color: var(--text-2); border-radius: 999px; padding: 2px 10px; font-size: 12px; cursor: pointer; }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  .chip.inherited { background: var(--surface-3); color: var(--text-muted); cursor: not-allowed; }
  .sentence { grid-column: 2; margin: 0; font-size: 12px; color: var(--text-2); }
  .ok { color: var(--ok-text); }
  .missing { color: var(--err-text); }
  .muted { color: var(--text-muted); font-size: 12px; margin: 0; }
</style>
