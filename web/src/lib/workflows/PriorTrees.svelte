<script lang="ts">
  /**
   * The prior tree editor.
   *
   * A stochastic semantic field has no value in the GIS data, so one has to be
   * sampled for every building. This page builds the distribution it's sampled
   * from: pick which fields it depends on (any mix of semantic fields and raw GIS
   * columns), generate the table from the project's own buildings, adjust it, then
   * see what it produces before committing it to the project.
   */
  import { onMount } from 'svelte';
  import WorkflowGuide from '../components/WorkflowGuide.svelte';
  import ConditioningPicker from '../components/priorTrees/ConditioningPicker.svelte';
  import JointTableEditor from '../components/priorTrees/JointTableEditor.svelte';
  import NumericTableEditor from '../components/priorTrees/NumericTableEditor.svelte';
  import PriorTreeGraph from '../components/priorTrees/PriorTreeGraph.svelte';
  import SamplePreview from '../components/priorTrees/SamplePreview.svelte';
  import WeightBar from '../components/priorTrees/WeightBar.svelte';
  import { priorTreesStore, jointFor, priorTargets } from '../stores/priorTreesStore';
  import { semanticFieldsStore } from '../stores/semanticFieldsStore';
  import { loadSavedArtifact, markSaved, savedAt } from '../stores/projectArtifacts';
  import { formatSavedAt, saveArtifact } from '../api/artifacts';
  import {
    exportPriorTreeYaml,
    fetchConditioningFields,
    fetchRegistrySuggestions,
    generatePrior,
    previewConditioning,
    samplePriorTree,
    validatePriorTree,
  } from '../api/priorTrees';
  import type {
    ConditionPreview,
    ConditioningCandidate,
    Distribution,
    GeneratedKey,
    GenerationMethod,
    PriorConfig,
  } from '../types/priorTrees';
  import { distributionTotal } from '../utils/priorViz';
  import { isConditionalPrior } from '../types/priorTrees';
  import type { PriorTreeTemplateSummary } from '../types/priorTrees';
  import { downloadText } from '../utils/download';

  let templates: PriorTreeTemplateSummary[] = [];
  let candidates: ConditioningCandidate[] = [];
  let rowCount = 0;
  let hasGisData = false;

  let conditionOn: string[] = [];
  let method: GenerationMethod = 'uniform';
  let observedColumn = '';
  let minCount = 5;
  let conditionPreview: ConditionPreview | null = null;

  /** Per-key evidence from the last generation, kept so the table can show its provenance. */
  let evidence: Record<string, GeneratedKey[]> = {};
  let generationWarnings: string[] = [];

  let sampleSize = 2000;
  let sampleSeed = 0;

  /** Retrofit packages moved to their own page; only the priors view remains. */
  const tab = 'priors' as const;

  let loadingTemplates = true;
  let generating = false;
  let validating = false;
  let sampling = false;
  let saving = false;
  let error: string | null = null;
  let notice: string | null = null;

  $: fields = $semanticFieldsStore.fields;
  $: stochasticFields = fields.filter((field) => field.type === 'stochastic' && field.requiresPrior);
  $: config = $priorTreesStore.config;
  $: selectedTarget = $priorTreesStore.selectedTarget;
  $: configuredTargets = priorTargets(config);

  /** Every field that could take a prior: the stochastic ones, plus anything already configured. */
  $: targets = [
    ...stochasticFields.map((field) => field.name),
    ...configuredTargets.filter((target) => !stochasticFields.some((field) => field.name === target)),
  ];

  $: targetStatus = Object.fromEntries(targets.map((target) => [target, statusFor(target, config)]));
  $: selectedJoint = selectedTarget ? jointFor(config, selectedTarget) : null;
  $: selectedPrior = selectedTarget ? config.priors[selectedTarget] ?? null : null;
  /** A numeric target conditioned on a combination: one normal per branch. */
  $: selectedConditional = isConditionalPrior(selectedPrior) ? selectedPrior : null;
  $: selectedUnconditional =
    selectedPrior && !isConditionalPrior(selectedPrior) ? selectedPrior : null;
  $: targetValues = selectedTarget ? valuesFor(selectedTarget) : [];
  $: observedCandidates = candidates.filter(
    (candidate) => candidate.source !== 'sampled' && candidate.presentCount > 0
  );

  onMount(async () => {
    await Promise.all([loadTemplates(), refreshCandidates()]);
    if (!selectedTarget && targets.length > 0) selectTarget(targets[0]);
  });

  /** The target's possible values: its semantic field options, else whatever the registry declares. */
  function valuesFor(target: string): string[] {
    const field = fields.find((entry) => entry.name === target);
    if (field?.options?.length) return field.options;
    const declared = config.registry.fields.find((entry) => entry.name === target);
    return declared?.values ?? [];
  }

  /**
   * Whether the target takes a categorical or a numeric prior. Declared options are
   * what decide it -- a field's `dataType` describes the GIS column it reads, which
   * is numeric even for a field whose own values are buckets.
   */
  function dtypeFor(target: string): 'categorical' | 'numeric' {
    if (valuesFor(target).length > 0) return 'categorical';
    const field = fields.find((entry) => entry.name === target);
    if (field) return field.dataType === 'numeric' ? 'numeric' : 'categorical';
    return config.registry.fields.find((entry) => entry.name === target)?.dtype ?? 'categorical';
  }

  async function loadTemplates() {
    loadingTemplates = true;
    try {
      const response = await fetch('/api/prior-trees/templates');
      templates = (await response.json()).templates || [];
    } catch {
      error = 'Failed to load prior tree templates.';
    } finally {
      loadingTemplates = false;
    }
  }

  async function refreshCandidates() {
    try {
      const data = await fetchConditioningFields(fields);
      candidates = data.candidates;
      rowCount = data.rowCount;
      hasGisData = data.hasGisData;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to read the project fields.';
    }
  }

  /** Opening a target loads whatever conditioning its existing prior already uses. */
  function selectTarget(target: string) {
    priorTreesStore.setSelectedTarget(target);
    conditionOn = conditionsOf(target);
    generationWarnings = [];
    notice = null;
    observedColumn = guessObservedColumn(target);
    void refreshConditionPreview();
  }

  /** What a target's existing prior is conditioned on, in either of the two shapes. */
  function conditionsOf(target: string): string[] {
    const joint = jointFor(config, target);
    if (joint) return [...joint.condition_on];
    const prior = config.priors[target];
    if (!isConditionalPrior(prior)) return [];
    const key = config.priors[prior.source_feature];
    const fields = key && !isConditionalPrior(key)
      ? (key.sampler.features_to_concatenate as string[] | undefined)
      : undefined;
    return fields ? [...fields] : [prior.source_feature];
  }

  /** A column whose name looks like the target is the usual source for estimating it. */
  function guessObservedColumn(target: string): string {
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
    if (!selectedTarget) return;
    const dtype = dtypeFor(selectedTarget);
    if (dtype === 'categorical' && targetValues.length === 0) {
      error = `'${selectedTarget}' has no possible values. Add options to the semantic field first.`;
      return;
    }

    generating = true;
    error = null;
    notice = null;
    try {
      const generated = await generatePrior(fields, {
        target: selectedTarget,
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
        priorTreesStore.setPriorEntries(selectedTarget, generated.priors);
      } else if (generated.prior) {
        priorTreesStore.setPrior(selectedTarget, generated.prior);
      }

      evidence = { ...evidence, [selectedTarget]: generated.keys };
      generationWarnings = generated.warnings;
      await syncRegistry();
      notice = `Generated a prior for ${selectedTarget}.`;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to generate the prior.';
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

  async function validate() {
    validating = true;
    error = null;
    try {
      const result = await validatePriorTree(
        config,
        stochasticFields.map((field) => field.name)
      );
      priorTreesStore.setValidation(result);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to validate the prior tree.';
    } finally {
      validating = false;
    }
  }

  async function runSample() {
    sampling = true;
    error = null;
    try {
      priorTreesStore.setSample(await samplePriorTree(fields, config, sampleSize, sampleSeed));
    } catch (e) {
      priorTreesStore.setSample(null);
      error = e instanceof Error ? e.message : 'Failed to sample the prior tree.';
    } finally {
      sampling = false;
    }
  }

  async function saveToProject() {
    saving = true;
    error = null;
    try {
      const file = await saveArtifact('priors', config as unknown as Record<string, unknown>);
      markSaved('priors', file.modifiedAt);
      notice = 'Saved to priors/priors.yaml.';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to save to the project.';
    } finally {
      saving = false;
    }
  }

  async function loadFromProject() {
    error = null;
    try {
      if (!(await loadSavedArtifact('priors'))) {
        error = 'No priors have been saved in this project yet.';
      }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load the saved priors.';
    }
  }

  async function loadTemplate(filename: string) {
    try {
      const response = await fetch(`/api/prior-trees/templates/${filename}`);
      priorTreesStore.loadFromTemplate(await response.json(), filename);
      const first = priorTargets($priorTreesStore.config)[0];
      if (first) selectTarget(first);
    } catch {
      error = 'Failed to load the template.';
    }
  }

  async function exportYaml() {
    try {
      downloadText(await exportPriorTreeYaml(config), 'priors.yml', 'application/x-yaml');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to export the prior tree.';
    }
  }

  function updateUnconditionalWeight(value: string, raw: string) {
    if (!selectedTarget || !selectedUnconditional) return;
    const weight = Number(raw);
    if (!Number.isFinite(weight) || weight < 0) return;
    const sampler = selectedUnconditional.sampler as { values?: string[]; weights?: number[] };
    const values = sampler.values ?? [];
    const weights = [...(sampler.weights ?? [])];
    const index = values.indexOf(value);
    if (index < 0) return;
    weights[index] = weight;
    priorTreesStore.setPrior(selectedTarget, { sampler: { ...sampler, values, weights } });
  }

  /** An unconditional categorical sampler as a `{value: weight}` map, for the bar. */
  function samplerDistribution(sampler: Record<string, unknown>): Distribution {
    const values = (sampler.values as string[]) ?? [];
    const weights = (sampler.weights as number[]) ?? [];
    return Object.fromEntries(values.map((value, index) => [value, Number(weights[index] ?? 0)]));
  }

  function statusFor(target: string, current: PriorConfig): string {
    const joint = jointFor(current, target);
    if (joint) {
      const rows = Object.keys(joint.table).length;
      return `on ${joint.condition_on.join(' · ')} · ${rows} ${rows === 1 ? 'row' : 'rows'}`;
    }
    const prior = current.priors[target];
    if (isConditionalPrior(prior)) {
      const rows = prior.conditions.length;
      return `on ${conditionsOf(target).join(' · ')} · ${rows} ${rows === 1 ? 'row' : 'rows'}`;
    }
    return prior ? 'unconditioned' : 'no prior yet';
  }
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Prior Trees</h1>
    <p class="subtitle">
      Generate distributions for stochastic semantic fields from your GIS data and semantic fields
    </p>
  </div>

  <div class="workflow-content">
    {#if stochasticFields.length === 0 && configuredTargets.length === 0}
      <WorkflowGuide
        title="Add stochastic semantic fields first"
        message="Prior trees are only needed for stochastic semantic fields such as heating or cooling systems — the ones your GIS data doesn't record. Define those fields before building priors."
        actionLabel="Go to Semantic Fields"
        actionWorkflow="semantic-fields"
      />
    {:else}
      <div class="toolbar panel">
        <div class="toolbar-group">
          <button type="button" class="secondary" onclick={() => priorTreesStore.startFromScratch()}>
            Start from scratch
          </button>
          {#if !loadingTemplates}
            {#each templates as template}
              <button type="button" class="secondary" onclick={() => loadTemplate(template.filename)}>
                Load "{template.name}"
              </button>
            {/each}
          {/if}
          {#if $savedAt['priors']}
            <button type="button" class="secondary" onclick={loadFromProject}>Revert to saved</button>
          {/if}
        </div>
        <div class="toolbar-group">
          <button type="button" onclick={validate} disabled={validating}>
            {validating ? 'Validating...' : 'Validate'}
          </button>
          <button type="button" onclick={saveToProject} disabled={saving}>
            {saving ? 'Saving...' : 'Save to project'}
          </button>
          <button type="button" class="secondary" onclick={exportYaml}>Export YAML</button>
        </div>
      </div>

      <p class="saved-status">{formatSavedAt($savedAt['priors'])}</p>


      {#if tab === 'priors'}
      <div class="panel">
        <h2>Fields needing a prior</h2>
        <div class="targets">
          {#each targets as target}
            <button
              type="button"
              class="target"
              class:active={selectedTarget === target}
              class:configured={configuredTargets.includes(target)}
              onclick={() => selectTarget(target)}
            >
              <span class="target-name">{target}</span>
              <span class="target-status">{targetStatus[target]}</span>
            </button>
          {/each}
        </div>
      </div>

      {#if selectedTarget}
        <div class="panel">
          <h2>Generate <span class="target-in-title">{selectedTarget}</span></h2>

          {#if !hasGisData}
            <p class="hint">
              No GIS data is loaded in this project. You can still author a prior by hand, but
              combinations can't be counted from your stock.
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

          <div class="method">
            <fieldset>
              <legend>Weights</legend>
              <label class="radio">
                <input type="radio" bind:group={method} value="uniform" />
                <span>
                  <strong>Even split</strong>
                  <small>Every value equally likely — a starting point to edit by hand.</small>
                </span>
              </label>
              <label class="radio">
                <input type="radio" bind:group={method} value="empirical" disabled={observedCandidates.length === 0} />
                <span>
                  <strong>Estimate from data</strong>
                  <small>
                    Count the weights from a column that already records this field for some buildings.
                  </small>
                </span>
              </label>
            </fieldset>

            {#if method === 'empirical'}
              <div class="empirical-options">
                <label>
                  <span>Observed in column</span>
                  <select bind:value={observedColumn}>
                    <option value="">Select a column...</option>
                    {#each observedCandidates as candidate}
                      <option value={candidate.name}>
                        {candidate.name} ({candidate.presentCount.toLocaleString()} rows)
                      </option>
                    {/each}
                  </select>
                </label>
                <label>
                  <span>Minimum observations per combination</span>
                  <input type="number" min="1" step="1" bind:value={minCount} />
                  <small>Thinner combinations inherit the overall distribution instead.</small>
                </label>
              </div>
            {/if}

            <button
              type="button"
              onclick={generate}
              disabled={generating || (method === 'empirical' && !observedColumn)}
            >
              {generating ? 'Generating...' : 'Generate prior'}
            </button>
          </div>

          {#if generationWarnings.length > 0}
            <ul class="warnings">
              {#each generationWarnings as warning}
                <li>{warning}</li>
              {/each}
            </ul>
          {/if}
        </div>

        {#if selectedJoint}
          <div class="panel">
            <h2>{selectedTarget} by {selectedJoint.condition_on.join(' · ')}</h2>
            <p class="panel-hint">
              Each row is one combination of {selectedJoint.condition_on.join(' and ')}, and each cell
              is the chance a building in that combination gets that value.
            </p>
            <JointTableEditor
              joint={selectedJoint}
              values={targetValues.length ? targetValues : Object.keys(selectedJoint.fallback ?? {})}
              evidence={evidence[selectedTarget] ?? []}
              onCellChange={(key, weights) => priorTreesStore.setTableRow(selectedTarget, key, weights)}
              onFallbackChange={(weights) => priorTreesStore.setFallback(selectedTarget, weights)}
              onRemoveRow={(key) => priorTreesStore.removeTableRow(selectedTarget, key)}
            />
          </div>
        {:else if selectedConditional}
          <div class="panel">
            <h2>{selectedTarget} by {conditionsOf(selectedTarget).join(' · ')}</h2>
            <p class="panel-hint">
              Each row is one combination, with its own normal distribution. A building in that
              combination draws {selectedTarget} from the row's mean and spread.
            </p>
            <NumericTableEditor
              prior={selectedConditional}
              target={selectedTarget}
              evidence={evidence[selectedTarget] ?? []}
              onSamplerChange={(key, sampler) =>
                priorTreesStore.setConditionSampler(selectedTarget, key, sampler)}
              onFallbackChange={(sampler) =>
                priorTreesStore.setConditionFallback(selectedTarget, sampler)}
              onRemove={(key) => priorTreesStore.removeCondition(selectedTarget, key)}
            />
            <button
              type="button"
              class="secondary danger"
              onclick={() => priorTreesStore.removeTarget(selectedTarget)}
            >
              Remove this prior
            </button>
          </div>
        {:else if selectedUnconditional}
          {@const sampler = selectedUnconditional.sampler}
          <div class="panel">
            <h2>{selectedTarget}</h2>
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
              <p class="panel-hint">Weights sum to {distributionTotal(distribution).toFixed(2)}.</p>
            {:else}
              <p class="panel-hint">
                Numeric prior: normal with mean {String(sampler.mean)}, sd {String(sampler.std)}, clipped
                to {String(sampler.clip_min ?? '-inf')}–{String(sampler.clip_max ?? 'inf')}.
              </p>
            {/if}
            <button
              type="button"
              class="secondary danger"
              onclick={() => priorTreesStore.removeTarget(selectedTarget)}
            >
              Remove this prior
            </button>
          </div>
        {/if}
      {/if}

      {/if}

      {#if $priorTreesStore.validationErrors.length > 0}
        <div class="panel invalid">
          <h2>Problems</h2>
          <ul>
            {#each $priorTreesStore.validationErrors as issue}
              <li>{issue}</li>
            {/each}
          </ul>
        </div>
      {:else if $priorTreesStore.valid}
        <div class="panel success">
          <p>Every stochastic field has a valid prior. This tree will sample.</p>
        </div>
      {/if}

      {#if $priorTreesStore.validationWarnings.length > 0}
        <div class="panel caution">
          <h2>Worth checking</h2>
          <ul>
            {#each $priorTreesStore.validationWarnings as warning}
              <li>{warning}</li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if tab === 'priors' && $priorTreesStore.dependencies.nodes.length > 0}
        <div class="panel">
          <h2>Sampling order</h2>
          <PriorTreeGraph graph={$priorTreesStore.dependencies} />
        </div>
      {/if}

      {#if tab === 'priors' && configuredTargets.length > 0}
        <div class="panel">
          <div class="sample-header">
            <h2>Preview</h2>
            <div class="sample-controls">
              <label>
                <span>Buildings</span>
                <input type="number" min="1" max="20000" step="100" bind:value={sampleSize} />
              </label>
              <label>
                <span>Seed</span>
                <input type="number" step="1" bind:value={sampleSeed} />
              </label>
              <button type="button" onclick={runSample} disabled={sampling}>
                {sampling ? 'Sampling...' : 'Sample'}
              </button>
            </div>
          </div>

          {#if $priorTreesStore.sample}
            <SamplePreview sample={$priorTreesStore.sample} />
          {:else}
            <p class="panel-hint">
              Draw from this prior over your own buildings to see what it produces before saving it.
            </p>
          {/if}
        </div>
      {/if}
    {/if}

    {#if notice}
      <p class="notice">{notice}</p>
    {/if}
    {#if error}
      <p class="error">{error}</p>
    {/if}
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

  .subtitle {
    margin: 0;
    color: #6b7280;
    font-size: 14px;
  }

  .workflow-content {
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .panel {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .panel h2 {
    margin: 0;
    font-size: 18px;
  }

  .target-in-title {
    color: #2563eb;
  }

  .panel-hint {
    margin: 0;
    font-size: 13px;
    color: #6b7280;
    line-height: 1.5;
  }

  .toolbar {
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .toolbar-group {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .saved-status {
    margin: -16px 0 0;
    font-size: 12px;
    color: #6b7280;
  }

  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: -8px;
  }

  .tabs button {
    display: flex;
    align-items: center;
    gap: 7px;
    background: transparent;
    color: #6b7280;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 8px 14px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }

  .tabs button:hover {
    color: #374151;
  }

  .tabs button.active {
    color: #2563eb;
    border-bottom-color: #2563eb;
  }

  .tab-count {
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    background: #f3f4f6;
    border-radius: 999px;
    padding: 1px 7px;
  }

  .tabs button.active .tab-count {
    color: #1d4ed8;
    background: #dbeafe;
  }

  .targets {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
  }

  .target {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 14px;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #ffffff;
    text-align: left;
    cursor: pointer;
    font-weight: 400;
  }

  .target:hover {
    border-color: #93c5fd;
  }

  .target.active {
    border-color: #2563eb;
    background: #eff6ff;
  }

  .target-name {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
  }

  .target-status {
    font-size: 12px;
    color: #9ca3af;
  }

  .target.configured .target-status {
    color: #15803d;
  }

  .method {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding-top: 16px;
    border-top: 1px solid #f3f4f6;
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
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #6b7280;
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
    color: #111827;
  }

  .radio small {
    font-size: 12px;
    color: #6b7280;
    line-height: 1.4;
  }

  .empirical-options {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }

  .empirical-options label,
  .sample-controls label,
  .weight-inputs label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: #4b5563;
  }

  .empirical-options select,
  .empirical-options input,
  .sample-controls input,
  .weight-inputs input {
    padding: 6px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
  }

  .empirical-options small {
    font-size: 11px;
    color: #9ca3af;
  }

  .weight-inputs {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
  }

  .sample-header {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 12px;
  }

  .sample-controls {
    display: flex;
    align-items: flex-end;
    gap: 10px;
  }

  .sample-controls input {
    width: 96px;
  }

  button {
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    padding: 9px 16px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
  }

  button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  button.secondary {
    background: #ffffff;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  button.secondary:hover:not(:disabled) {
    background: #f3f4f6;
  }

  button.danger {
    color: #b91c1c;
    border-color: #fecaca;
    align-self: flex-start;
  }

  .warnings,
  .invalid ul,
  .caution ul {
    margin: 0;
    padding-left: 20px;
    font-size: 13px;
    line-height: 1.6;
  }

  .warnings {
    color: #92400e;
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

  .invalid {
    border-color: #fecaca;
    background: #fef2f2;
    color: #b91c1c;
  }

  .caution {
    border-color: #fde68a;
    background: #fffbeb;
    color: #92400e;
  }

  .success {
    border-color: #bbf7d0;
    background: #f0fdf4;
    color: #166534;
  }

  .success p {
    margin: 0;
    font-size: 13px;
  }

  .notice {
    margin: 0;
    font-size: 13px;
    color: #166534;
  }

  .error {
    margin: 0;
    font-size: 13px;
    color: #dc2626;
  }
</style>
