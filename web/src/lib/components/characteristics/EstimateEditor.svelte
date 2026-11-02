<script module lang="ts">
  import type { GeneratedKey } from '../../types/priorTrees';
  /** Per-target evidence from the last generation, kept across remounts so the table
   * can still show where each row came from after switching characteristics. */
  const evidenceByTarget = new Map<string, GeneratedKey[]>();
</script>

<script lang="ts">
  /**
   * The estimate (GloBI: prior) for one characteristic your data doesn't record:
   * what its odds depend on, a generated starting table (even split or counted from
   * an observed column), and the table itself to adjust. Used by the characteristic
   * card and by the Prior Trees page.
   */
  import { onMount, untrack } from 'svelte';
  import ConditioningPicker from '../priorTrees/ConditioningPicker.svelte';
  import JointTableEditor from '../priorTrees/JointTableEditor.svelte';
  import NumericTableEditor from '../priorTrees/NumericTableEditor.svelte';
  import SamplePreview from '../priorTrees/SamplePreview.svelte';
  import WeightBar from '../priorTrees/WeightBar.svelte';
  import Explain from '../Explain.svelte';
  import Select from '../Select.svelte';
  import { priorTreesStore, jointFor } from '../../stores/priorTreesStore';
  import { semanticFieldsStore } from '../../stores/semanticFieldsStore';
  import {
    fetchConditioningFields,
    fetchRegistrySuggestions,
    generatePrior,
    previewConditioning,
    samplePriorTree,
  } from '../../api/priorTrees';
  import {
    isConditionalPrior,
    type ConditionPreview,
    type ConditioningCandidate,
    type Distribution,
    type GenerationMethod,
    type SampleSummary,
  } from '../../types/priorTrees';
  import { distributionTotal } from '../../utils/priorViz';
  import { dependsOn } from '../../utils/characteristics';
  import { HELP } from '../../help';
  const help = HELP.priorTrees;

  let {
    target,
    asCounts = false,
    showPreview = false,
  }: {
    target: string;
    /** Show table weights as "buildings out of 100" instead of 0–1 shares. */
    asCounts?: boolean;
    /** Offer a sample of this characteristic alone (the Prior Trees page samples everything). */
    showPreview?: boolean;
  } = $props();

  let candidates = $state<ConditioningCandidate[]>([]);
  let rowCount = $state(0);
  let hasGisData = $state(true);
  let conditionOn = $state<string[]>([]);
  let method = $state<GenerationMethod>('uniform');
  let observedColumn = $state('');
  let minCount = $state(5);
  let conditionPreview = $state<ConditionPreview | null>(null);
  let generationWarnings = $state<string[]>([]);
  // The parent keys this editor on the target, so the initial value is the only one.
  let evidence = $state<GeneratedKey[]>(untrack(() => evidenceByTarget.get(target) ?? []));
  let generating = $state(false);
  let sampling = $state(false);
  let sample = $state<SampleSummary | null>(null);
  let error = $state<string | null>(null);
  let notice = $state<string | null>(null);

  const fields = $derived($semanticFieldsStore.fields);
  const config = $derived($priorTreesStore.config);
  const joint = $derived(jointFor(config, target));
  const prior = $derived(config.priors[target] ?? null);
  /** A numeric target conditioned on a combination: one normal per branch. */
  const conditional = $derived(isConditionalPrior(prior) ? prior : null);
  const unconditional = $derived(prior && !isConditionalPrior(prior) ? prior : null);
  const targetValues = $derived(valuesFor(target));
  const observedCandidates = $derived(
    candidates.filter((candidate) => candidate.source !== 'sampled' && candidate.presentCount > 0)
  );
  const deps = $derived(dependsOn(config, target));
  const tableHelp = $derived(
    joint
      ? `Each row is one combination of ${joint.condition_on.join(' and ')}; each cell is how many buildings like that get the value.`
      : `Each row is one combination, with its own normal distribution. A building in that combination draws ${target} from the row's mean and spread.`
  );

  onMount(async () => {
    conditionOn = dependsOn(config, target);
    try {
      const data = await fetchConditioningFields(fields);
      candidates = data.candidates;
      rowCount = data.rowCount;
      hasGisData = data.hasGisData;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to read the project fields.';
    }
    observedColumn = guessObservedColumn();
    void refreshConditionPreview();
  });

  /** The target's possible values: its field options, else whatever the registry declares. */
  function valuesFor(name: string): string[] {
    const field = fields.find((entry) => entry.name === name);
    if (field?.options?.length) return field.options;
    return config.registry.fields.find((entry) => entry.name === name)?.values ?? [];
  }

  /**
   * Whether the target takes a categorical or a numeric prior. Declared options decide
   * it -- a field's `dataType` describes the GIS column it reads, which is numeric even
   * for a field whose own values are buckets.
   */
  function dtypeFor(): 'categorical' | 'numeric' {
    if (targetValues.length > 0) return 'categorical';
    const field = fields.find((entry) => entry.name === target);
    if (field) return field.dataType === 'numeric' ? 'numeric' : 'categorical';
    return config.registry.fields.find((entry) => entry.name === target)?.dtype ?? 'categorical';
  }

  /** A column whose name looks like the target is the usual source for estimating it. */
  function guessObservedColumn(): string {
    const normalized = target.toLowerCase().replace(/[^a-z0-9]/g, '');
    const match = observedCandidates.find(
      (candidate) => candidate.name.toLowerCase().replace(/[^a-z0-9]/g, '') === normalized
    );
    return match?.name ?? '';
  }

  async function refreshConditionPreview() {
    if (conditionOn.length === 0) {
      conditionPreview = null;
      return;
    }
    try {
      conditionPreview = await previewConditioning(fields, conditionOn);
    } catch {
      conditionPreview = null;
    }
  }

  function toggleCondition(name: string) {
    conditionOn = conditionOn.includes(name)
      ? conditionOn.filter((entry) => entry !== name)
      : [...conditionOn, name];
    void refreshConditionPreview();
  }

  function reorderConditions(names: string[]) {
    conditionOn = names;
    void refreshConditionPreview();
  }

  async function generate() {
    const dtype = dtypeFor();
    if (dtype === 'categorical' && targetValues.length === 0) {
      error = `'${target}' has no possible values. Add its values first.`;
      return;
    }
    generating = true;
    error = null;
    notice = null;
    try {
      const generated = await generatePrior(fields, {
        target,
        targetValues,
        conditionOn,
        method,
        observedColumn: method === 'empirical' ? observedColumn : null,
        dtype,
        minCount,
      });

      if (generated.mode === 'joint' && generated.joint) {
        priorTreesStore.setJoint(generated.joint);
      } else if (Object.keys(generated.priors ?? {}).length > 0) {
        priorTreesStore.setPriorEntries(target, generated.priors);
      } else if (generated.prior) {
        priorTreesStore.setPrior(target, generated.prior);
      }

      evidence = generated.keys;
      evidenceByTarget.set(target, generated.keys);
      generationWarnings = generated.warnings;
      await syncRegistry();
      notice = `Generated an estimate for ${target}.`;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to generate the estimate.';
    } finally {
      generating = false;
    }
  }

  /** Declare any field the config now references, so the registry stays complete. */
  async function syncRegistry() {
    try {
      const additions = await fetchRegistrySuggestions(fields, $priorTreesStore.config);
      priorTreesStore.mergeRegistryFields(additions);
    } catch {
      // A missing registry entry is reported by validation, so this is not fatal.
    }
  }

  async function runSample() {
    sampling = true;
    error = null;
    try {
      const result = await samplePriorTree(fields, config, 2000, 0);
      sample = { ...result, distributions: result.distributions.filter((entry) => entry.feature === target) };
    } catch (e) {
      sample = null;
      error = e instanceof Error ? e.message : 'Failed to sample.';
    } finally {
      sampling = false;
    }
  }

  function updateUnconditionalWeight(value: string, raw: string) {
    if (!unconditional) return;
    const weight = Number(raw);
    if (!Number.isFinite(weight) || weight < 0) return;
    const sampler = unconditional.sampler as { values?: string[]; weights?: number[] };
    const values = sampler.values ?? [];
    const weights = [...(sampler.weights ?? [])];
    const index = values.indexOf(value);
    if (index < 0) return;
    weights[index] = weight;
    priorTreesStore.setPrior(target, { sampler: { ...sampler, values, weights } });
  }

  /** An unconditional categorical sampler as a `{value: weight}` map, for the bar. */
  function samplerDistribution(sampler: Record<string, unknown>): Distribution {
    const values = (sampler.values as string[]) ?? [];
    const weights = (sampler.weights as number[]) ?? [];
    return Object.fromEntries(values.map((value, index) => [value, Number(weights[index] ?? 0)]));
  }
</script>

<div class="estimate">
  <div class="block">
    <h4>Depends on <span class="globi">(conditioning)</span> <Explain text={help.generate} tip /></h4>
    <Explain text={help.generate} />
    {#if !hasGisData}
      <p class="hint">
        No GIS data is loaded in this project. You can still set the odds by hand, but combinations can't be
        counted from your buildings.
      </p>
    {/if}
    <ConditioningPicker
      {candidates}
      selected={conditionOn}
      preview={conditionPreview}
      {rowCount}
      onToggle={toggleCondition}
      onReorder={reorderConditions}
    />
  </div>

  <div class="block method">
    <fieldset>
      <legend>Starting odds</legend>
      <label class="radio">
        <input type="radio" bind:group={method} value="uniform" />
        <span>
          <strong>Even split</strong>
          <small>Every value equally likely, a starting point to edit by hand.</small>
        </span>
      </label>
      <label class="radio">
        <input type="radio" bind:group={method} value="empirical" disabled={observedCandidates.length === 0} />
        <span>
          <strong>Estimate from data</strong>
          <small>Count the odds from a column that already records this for some buildings.</small>
        </span>
      </label>
    </fieldset>

    {#if method === 'empirical'}
      <div class="empirical-options">
        <label>
          <span>Observed in column</span>
          <Select
            value={observedColumn}
            options={observedCandidates.map((candidate) => ({
              value: candidate.name,
              label: `${candidate.name} (${candidate.presentCount.toLocaleString()} rows)`,
            }))}
            placeholder="Select a column…"
            onChange={(value) => (observedColumn = value)}
          />
        </label>
        <label>
          <span>Minimum buildings per combination</span>
          <input type="number" min="1" step="1" bind:value={minCount} />
          <small>Combinations with fewer use “Everything else” instead.</small>
        </label>
      </div>
    {/if}

    <button
      type="button"
      class="btn"
      onclick={generate}
      disabled={generating || (method === 'empirical' && !observedColumn)}
    >
      {generating ? 'Generating…' : prior || joint ? 'Regenerate the odds' : 'Generate the odds'}
    </button>

    {#if generationWarnings.length > 0}
      <ul class="warnings">
        {#each generationWarnings as warning}
          <li>{warning}</li>
        {/each}
      </ul>
    {/if}
  </div>

  {#if joint}
    <div class="block">
      <h4>Odds of {target} by {joint.condition_on.join(' · ')} <Explain text={tableHelp} tip /></h4>
      <Explain text={tableHelp} />
      <JointTableEditor
        {joint}
        values={targetValues.length ? targetValues : Object.keys(joint.fallback ?? {})}
        {evidence}
        {asCounts}
        onCellChange={(key, weights) => priorTreesStore.setTableRow(target, key, weights)}
        onFallbackChange={(weights) => priorTreesStore.setFallback(target, weights)}
        onRemoveRow={(key) => priorTreesStore.removeTableRow(target, key)}
      />
    </div>
  {:else if conditional}
    <div class="block">
      <h4>{target} by {deps.join(' · ')} <Explain text={tableHelp} tip /></h4>
      <Explain text={tableHelp} />
      <NumericTableEditor
        prior={conditional}
        {target}
        {evidence}
        onSamplerChange={(key, sampler) => priorTreesStore.setConditionSampler(target, key, sampler)}
        onFallbackChange={(sampler) => priorTreesStore.setConditionFallback(target, sampler)}
        onRemove={(key) => priorTreesStore.removeCondition(target, key)}
      />
    </div>
  {:else if unconditional}
    {@const sampler = unconditional.sampler}
    <div class="block">
      <h4>Odds of {target}, the same for every building</h4>
      {#if sampler.values}
        {@const distribution = samplerDistribution(sampler)}
        <WeightBar {distribution} order={(sampler.values as string[]) ?? []} />
        <div class="weight-inputs">
          {#each (sampler.values as string[]) ?? [] as value}
            <label>
              <span>{value}</span>
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={Number(distribution[value] ?? 0)}
                onchange={(event) => updateUnconditionalWeight(value, event.currentTarget.value)}
              />
            </label>
          {/each}
        </div>
        <p class="hint">Weights sum to {distributionTotal(distribution).toFixed(2)}.</p>
      {:else}
        <p class="hint">
          Numeric: normal with mean {String(sampler.mean)}, sd {String(sampler.std)}, clipped to
          {String(sampler.clip_min ?? '-inf')}–{String(sampler.clip_max ?? 'inf')}.
        </p>
      {/if}
    </div>
  {/if}

  {#if prior || joint}
    <div class="row">
      {#if showPreview}
        <button type="button" class="btn btn-secondary" onclick={runSample} disabled={sampling}>
          {sampling ? 'Drawing…' : 'Preview 2,000 draws'}
        </button>
      {/if}
      <button type="button" class="btn btn-danger" onclick={() => priorTreesStore.removeTarget(target)}>
        Remove the estimate
      </button>
    </div>
  {/if}

  {#if sample}
    <div class="block">
      <SamplePreview {sample} />
    </div>
  {/if}

  {#if notice}<p class="hint">{notice}</p>{/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

<style>
  .estimate {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h4 {
    margin: 0;
    font-size: var(--text-md);
  }

  .globi {
    font-weight: 400;
    color: var(--text-muted);
  }

  .hint {
    margin: 0;
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
  }

  .method {
    padding-top: var(--space-4);
    border-top: 1px solid var(--surface-3);
    align-items: flex-start;
  }

  fieldset {
    border: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }

  legend {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    padding: 0 0 8px;
  }

  .radio {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    max-width: 320px;
    cursor: pointer;
  }

  .radio span {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .radio strong {
    font-size: 13px;
    color: var(--text);
  }

  .radio small {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .empirical-options {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }

  .empirical-options label,
  .weight-inputs label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--text-2);
  }

  .empirical-options small {
    font-size: 11px;
    color: var(--text-faint);
  }

  .weight-inputs {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
  }

  .warnings {
    margin: 0;
    padding-left: 18px;
    font-size: 13px;
    color: var(--warn-text);
  }

  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
</style>
