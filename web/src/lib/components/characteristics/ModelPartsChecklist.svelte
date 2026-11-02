<script lang="ts">
  /**
   * Which model parts one characteristic chooses (GloBI: its place in the component
   * map's selectors), as plain checkboxes, plus the library records each ticked part
   * needs. Ticking writes selectors through setPartForField, so a part that only
   * inherited a parent's choice gets its own override and its siblings are untouched.
   */
  import { componentMapStore } from '../../stores/componentMapStore';
  import { componentTreeStore } from '../../stores/componentTreeStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import { MODEL_PARTS, defaultSuffix, otherPaths, type ModelPart } from '../../utils/modelParts';
  import {
    buildEmptyComponentMap,
    fieldStatusAtPath,
    getSelectorAtPath,
    setPartForField,
  } from '../../utils/componentMapTree';
  import SelectorCoverageGrid from '../componentMap/SelectorCoverageGrid.svelte';
  import SchemaForm from '../componentLibrary/SchemaForm.svelte';

  let {
    fieldName,
    fieldOrder,
    onShowConnections,
  }: {
    fieldName: string;
    /** Characteristic names in list order, for where a new field goes in a selector. */
    fieldOrder: string[];
    /** Open the All connections view at a component path. */
    onShowConnections: (path: string) => void;
  } = $props();

  const GROUPS = [
    { id: 'Envelope', label: 'Envelope' },
    { id: 'Systems', label: 'Systems' },
    { id: 'Use', label: 'How the building is used' },
  ] as const;

  const map = $derived($componentMapStore.map);
  const nodes = $derived($componentTreeStore.nodesByPath);
  const semanticFields = $derived(
    $semanticFieldsStore.fields.map((field) => ({ name: field.name, options: field.options }))
  );
  const moreParts = $derived(
    otherPaths(Object.keys(nodes)).map((path): ModelPart => ({
      id: path,
      label: nodes[path]?.displayName ?? path,
      group: 'Envelope',
      paths: [path],
    }))
  );

  let recordEdit = $state<{ name: string; exists: boolean; componentType: string } | null>(null);

  function statusOf(path: string) {
    return map ? fieldStatusAtPath(map, path, fieldName) : { status: 'off' as const };
  }

  function partState(part: ModelPart) {
    const paths = part.paths.filter((path) => nodes[path]);
    const statuses = paths.map((path) => ({ path, ...statusOf(path) }));
    const on = statuses.filter((entry) => entry.status !== 'off');
    const own = on.filter((entry) => entry.status === 'own').map((entry) => entry.path);
    return {
      paths,
      checked: paths.length > 0 && on.length === paths.length,
      partial: on.length > 0 && on.length < paths.length,
      // Reached only through a parent group: change it there, not here.
      inheritedFrom: own.length === 0 && on.length > 0 ? on[0].from : undefined,
      own,
    };
  }

  /** Paths whose existing record names would change: their own selector has other fields. */
  function renamedBy(part: ModelPart, on: boolean): boolean {
    if (!map) return false;
    return part.paths.some((path) => {
      const selector = getSelectorAtPath(map, path);
      if (!selector) return false;
      const has = selector.source_fields.includes(fieldName);
      return on ? !has : has && selector.source_fields.length > 1;
    });
  }

  function toggle(part: ModelPart, on: boolean) {
    if (
      renamedBy(part, on) &&
      !confirm(
        `This changes the record names for ${part.label}, so records already made for it will no longer be used. Continue?`
      )
    ) {
      return;
    }
    const base = map ?? buildEmptyComponentMap();
    const next = part.paths
      .filter((path) => nodes[path])
      .reduce((current, path) => {
        const status = fieldStatusAtPath(current, path, fieldName).status;
        if (on && status === 'off') {
          return setPartForField(current, path, fieldName, true, fieldOrder, defaultSuffix(path, nodes));
        }
        if (!on && status === 'own') return setPartForField(current, path, fieldName, false, fieldOrder);
        return current;
      }, base);
    componentMapStore.setMap(next);
  }

  function pattern(path: string): string {
    const selector = map ? getSelectorAtPath(map, path) : null;
    if (!selector) return '';
    const parts = selector.source_fields.map((name) => `‹${name}›`);
    return [...parts, ...(selector.suffix ? [selector.suffix] : [])].join('_');
  }
</script>

{#snippet partRow(part: ModelPart)}
  {@const state = partState(part)}
  {#if state.paths.length > 0}
    <li>
      <label class="part">
        <input
          type="checkbox"
          checked={state.checked}
          indeterminate={state.partial}
          disabled={Boolean(state.inheritedFrom)}
          onchange={(event) => toggle(part, (event.currentTarget as HTMLInputElement).checked)}
        />
        <span>{part.label}</span>
        {#if state.inheritedFrom}
          <span class="via">
            via {nodes[state.inheritedFrom]?.displayName ?? state.inheritedFrom}
            <button type="button" class="link" onclick={() => onShowConnections(state.inheritedFrom!)}>change</button>
          </span>
        {/if}
      </label>

      {#each state.own as path}
        {@const selector = map ? getSelectorAtPath(map, path) : null}
        {@const componentType = nodes[path]?.componentType}
        {#if selector && componentType}
          <details class="records">
            <summary>
              Records named <code>{pattern(path)}</code>
              {#if state.paths.length > 1}<span class="muted">({nodes[path]?.displayName})</span>{/if}
            </summary>
            <SelectorCoverageGrid
              {componentType}
              sourceFields={selector.source_fields}
              suffix={selector.suffix}
              {semanticFields}
              onOpenRecord={(name, exists) => (recordEdit = { name, exists, componentType })}
            />
          </details>
        {/if}
      {/each}
    </li>
  {/if}
{/snippet}

{#if recordEdit}
  <div class="record-edit">
    <button type="button" class="btn btn-ghost btn-sm" onclick={() => (recordEdit = null)}>← Back to model parts</button>
    <h4>{recordEdit.exists ? 'Edit' : 'New'} {recordEdit.componentType} <code>{recordEdit.name}</code></h4>
    {#key recordEdit.name}
      <SchemaForm
        componentType={recordEdit.componentType}
        mode={recordEdit.exists ? 'edit' : 'create'}
        name={recordEdit.exists ? recordEdit.name : null}
        presetName={recordEdit.name}
        onSaved={() => (recordEdit = null)}
        onCancel={() => (recordEdit = null)}
      />
    {/key}
  </div>
{:else if Object.keys(nodes).length === 0}
  <p class="muted">The model's component list hasn't loaded. Check that the backend is running.</p>
{:else}
  <div class="groups">
    {#each GROUPS as group}
      <div>
        <h5>{group.label}</h5>
        <ul>
          {#each MODEL_PARTS.filter((part) => part.group === group.id) as part (part.id)}
            {@render partRow(part)}
          {/each}
        </ul>
      </div>
    {/each}
  </div>
  <details class="more">
    <summary>More parts (schedules and parent groups)</summary>
    <ul>
      {#each moreParts as part (part.id)}
        {@render partRow(part)}
      {/each}
    </ul>
  </details>
{/if}

<style>
  .groups {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-4);
  }

  h5 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .part {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-sm);
    flex-wrap: wrap;
  }

  .via {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
    text-decoration: underline;
    font-size: inherit;
    font-weight: 400;
    cursor: pointer;
  }

  .records {
    margin: 4px 0 4px 24px;
    font-size: var(--text-sm);
  }

  .records summary {
    cursor: pointer;
    color: var(--text-2);
  }

  .more {
    margin-top: var(--space-4);
    font-size: var(--text-sm);
  }

  .more summary {
    cursor: pointer;
    color: var(--text-muted);
    margin-bottom: var(--space-2);
  }

  .muted {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .record-edit h4 {
    margin: var(--space-2) 0;
  }
</style>
