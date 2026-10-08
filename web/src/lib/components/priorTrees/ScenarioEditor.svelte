<script lang="ts">
  /**
   * Authoring scenarios.
   *
   * A scenario is a named set of overrides applied to an already-sampled stock:
   * "every building gets a heat pump", or "only the post-2003 stock does". Each
   * override is either a fixed value or a test on another field with a branch
   * either way, and anything downstream of a changed feature is resampled.
   */
  import {
    isConditionalOverride,
    KEEP_TOKEN,
    type ConditionalOverride,
    type ScenarioOverride,
    type ScenarioSpec,
    type ScenarioTarget,
  } from '../../types/priorTrees';

  export let scenarios: ScenarioSpec[] = [];
  export let targets: ScenarioTarget[] = [];
  export let onAdd: (name: string) => void;
  export let onUpdate: (index: number, updates: Partial<ScenarioSpec>) => void;
  export let onRemove: (index: number) => void;
  export let onSetOverride: (index: number, target: string, override: ScenarioOverride) => void;
  export let onRetarget: (index: number, from: string, to: string) => void;
  export let onRemoveOverride: (index: number, target: string) => void;

  let newName = '';

  /** Only sampled features can be overridden; context fields are read from GIS. */
  $: overridable = targets.filter((target) => !target.contextOnly);
  $: byName = new Map(targets.map((target) => [target.name, target]));

  function add() {
    const name = newName.trim() || 'New scenario';
    onAdd(name);
    newName = '';
  }

  function freeTarget(scenario: ScenarioSpec): string | null {
    return overridable.find((target) => !(target.name in scenario.overrides))?.name ?? null;
  }

  function addOverride(index: number, scenario: ScenarioSpec) {
    const target = freeTarget(scenario);
    if (!target) return;
    const values = byName.get(target)?.values ?? [];
    onSetOverride(index, target, { set: values[0] ?? '' });
  }

  /** Switching an override between the fixed and conditional forms. */
  function setKind(index: number, target: string, kind: 'fixed' | 'conditional') {
    const values = byName.get(target)?.values ?? [];
    if (kind === 'fixed') {
      onSetOverride(index, target, { set: values[0] ?? '' });
      return;
    }
    const source = targets[0]?.name ?? '';
    onSetOverride(index, target, {
      based_on: source,
      equals: byName.get(source)?.values[0] ?? '',
      then: values[0] ?? '',
      otherwise: KEEP_TOKEN,
    });
  }

  function updateConditional(
    index: number,
    target: string,
    override: ConditionalOverride,
    updates: Partial<ConditionalOverride>
  ) {
    onSetOverride(index, target, { ...override, ...updates });
  }

  /** The choices for a branch: any declared value, keep, or copy another field. */
  function branchOptions(target: string): Array<{ value: string; label: string }> {
    const values = byName.get(target)?.values ?? [];
    return [
      { value: KEEP_TOKEN, label: 'keep current value' },
      ...values.map((value) => ({ value, label: value })),
      ...targets
        .filter((entry) => entry.name !== target)
        .map((entry) => ({ value: `$${entry.name}`, label: `copy ${entry.name}` })),
    ];
  }

  function summarize(scenario: ScenarioSpec): string {
    const count = Object.keys(scenario.overrides).length;
    if (count === 0) return 'changes nothing yet';
    return Object.entries(scenario.overrides)
      .map(([target, override]) =>
        isConditionalOverride(override)
          ? `${target} where ${override.based_on}=${override.equals}`
          : `${target} → ${override.set}`
      )
      .join(' · ');
  }
</script>

<div class="scenarios">
  {#if overridable.length === 0}
    <p class="hint">
      Scenarios change features that a prior samples. Build at least one prior before
      writing a scenario.
    </p>
  {:else}
    {#each scenarios as scenario, index}
      <article class="scenario">
        <header>
          <label class="name">
            <span class="sr-only">Scenario name</span>
            <input
              type="text"
              value={scenario.name}
              onchange={(event) => onUpdate(index, { name: event.currentTarget.value })}
            />
          </label>
          <span class="summary">{summarize(scenario)}</span>
          <button type="button" class="remove" title="Delete this scenario" onclick={() => onRemove(index)}>
            Delete
          </button>
        </header>

        <div class="overrides">
          {#each Object.entries(scenario.overrides) as [target, override]}
            {@const conditional = isConditionalOverride(override) ? override : null}
            {@const fixed = isConditionalOverride(override) ? null : override}
            <div class="override">
              <div class="override-row">
                <label>
                  <span>Change</span>
                  <select
                    value={target}
                    onchange={(event) => onRetarget(index, target, event.currentTarget.value)}
                  >
                    {#each overridable as option}
                      <option value={option.name} disabled={option.name !== target && option.name in scenario.overrides}>
                        {option.name}
                      </option>
                    {/each}
                  </select>
                </label>

                <label>
                  <span>Rule</span>
                  <select
                    value={conditional ? 'conditional' : 'fixed'}
                    onchange={(event) =>
                      setKind(index, target, event.currentTarget.value === 'conditional' ? 'conditional' : 'fixed')}
                  >
                    <option value="fixed">for every building</option>
                    <option value="conditional">only where...</option>
                  </select>
                </label>

                {#if !conditional}
                  <label>
                    <span>To</span>
                    {#if (byName.get(target)?.values ?? []).length > 0}
                      <select
                        value={String(fixed?.set ?? '')}
                        onchange={(event) => onSetOverride(index, target, { set: event.currentTarget.value })}
                      >
                        {#each byName.get(target)?.values ?? [] as value}
                          <option {value}>{value}</option>
                        {/each}
                      </select>
                    {:else}
                      <input
                        type="number"
                        step="0.01"
                        value={String(fixed?.set ?? '')}
                        onchange={(event) => onSetOverride(index, target, { set: Number(event.currentTarget.value) })}
                      />
                    {/if}
                  </label>
                {/if}

                <button type="button" class="drop" title="Remove this change"
                        onclick={() => onRemoveOverride(index, target)}>×</button>
              </div>

              {#if conditional}
                <div class="override-row conditional">
                  <label>
                    <span>Where</span>
                    <select
                      value={conditional.based_on}
                      onchange={(event) =>
                        updateConditional(index, target, conditional, {
                          based_on: event.currentTarget.value,
                          equals: byName.get(event.currentTarget.value)?.values[0] ?? '',
                        })}
                    >
                      {#each targets as option}
                        <option value={option.name}>{option.name}</option>
                      {/each}
                    </select>
                  </label>
                  <label>
                    <span>Equals</span>
                    {#if (byName.get(conditional.based_on)?.values ?? []).length > 0}
                      <select
                        value={String(conditional.equals)}
                        onchange={(event) =>
                          updateConditional(index, target, conditional, { equals: event.currentTarget.value })}
                      >
                        {#each byName.get(conditional.based_on)?.values ?? [] as value}
                          <option {value}>{value}</option>
                        {/each}
                      </select>
                    {:else}
                      <input
                        type="text"
                        value={String(conditional.equals)}
                        onchange={(event) =>
                          updateConditional(index, target, conditional, { equals: event.currentTarget.value })}
                      />
                    {/if}
                  </label>
                  <label>
                    <span>Then</span>
                    <select
                      value={String(conditional.then)}
                      onchange={(event) =>
                        updateConditional(index, target, conditional, { then: event.currentTarget.value })}
                    >
                      {#each branchOptions(target) as option}
                        <option value={option.value}>{option.label}</option>
                      {/each}
                    </select>
                  </label>
                  <label>
                    <span>Otherwise</span>
                    <select
                      value={String(conditional.otherwise)}
                      onchange={(event) =>
                        updateConditional(index, target, conditional, { otherwise: event.currentTarget.value })}
                    >
                      {#each branchOptions(target) as option}
                        <option value={option.value}>{option.label}</option>
                      {/each}
                    </select>
                  </label>
                </div>
              {/if}
            </div>
          {/each}

          <button
            type="button"
            class="add-override"
            disabled={!freeTarget(scenario)}
            onclick={() => addOverride(index, scenario)}
          >
            + Add a change
          </button>
        </div>

        <footer>
          <label class="toggle">
            <input
              type="checkbox"
              checked={scenario.resample_changed_features ?? false}
              onchange={(event) =>
                onUpdate(index, { resample_changed_features: event.currentTarget.checked })}
            />
            <span>
              Resample the changed features too
              <small>
                Off (the usual choice) keeps the value this scenario set. On re-draws it from
                its prior, which only makes sense when the prior itself has changed.
              </small>
            </span>
          </label>
        </footer>
      </article>
    {/each}

    <div class="add-scenario">
      <label>
        <span class="sr-only">New scenario name</span>
        <input type="text" placeholder="Scenario name, e.g. Electrification" bind:value={newName} />
      </label>
      <button type="button" onclick={add}>Add scenario</button>
    </div>
  {/if}
</div>

<style>
  .scenarios {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .scenario {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .scenario header {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .name input {
    padding: 6px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    min-width: 220px;
  }

  .summary {
    flex: 1;
    font-size: 12px;
    color: #6b7280;
    min-width: 160px;
  }

  .remove {
    border: 1px solid #fecaca;
    background: #ffffff;
    color: #b91c1c;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }

  .remove:hover {
    background: #fef2f2;
  }

  .overrides {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .override {
    border-left: 3px solid #dbeafe;
    padding-left: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .override-row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 10px;
  }

  .override-row.conditional {
    padding-left: 14px;
    border-left: 1px dashed #e5e7eb;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 11px;
    color: #6b7280;
  }

  select,
  .override-row input {
    padding: 6px 8px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    background: #ffffff;
    color: #111827;
    min-width: 130px;
  }

  .drop {
    border: 1px solid #e5e7eb;
    background: #ffffff;
    color: #b91c1c;
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 13px;
    cursor: pointer;
    font-weight: 400;
  }

  .drop:hover {
    background: #fef2f2;
  }

  .add-override {
    align-self: flex-start;
    border: 1px dashed #d1d5db;
    background: #ffffff;
    color: #2563eb;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }

  .add-override:disabled {
    color: #9ca3af;
    cursor: not-allowed;
  }

  .add-override:not(:disabled):hover {
    background: #f8fafc;
  }

  .scenario footer {
    border-top: 1px solid #f3f4f6;
    padding-top: 10px;
  }

  .toggle {
    flex-direction: row;
    align-items: flex-start;
    gap: 8px;
    cursor: pointer;
  }

  .toggle span {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
    color: #374151;
  }

  .toggle small {
    font-size: 11px;
    color: #9ca3af;
    line-height: 1.4;
    max-width: 520px;
  }

  .add-scenario {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .add-scenario input {
    padding: 8px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    min-width: 280px;
  }

  .add-scenario button {
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }

  .hint {
    margin: 0;
    font-size: 13px;
    color: #92400e;
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 8px;
    padding: 10px 12px;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
</style>
