<script lang="ts">
  /**
   * "Describe it, then check it": the user writes what a field should be in plain
   * words, the backend asks Claude for a draft and runs it through the same validator
   * and preview as the editor (plus overlap / coverage checks). The draft is shown for
   * review and only touches the field when the user presses Apply; after that, the
   * normal Validate / Save flow takes over. The parent keys this on the field id, so
   * switching fields starts a fresh draft.
   */
  import { onMount } from 'svelte';
  import { draftSemanticField, fetchAssistStatus, type SemanticFieldDraft } from '../api/assist';
  import type { SemanticField } from '../types/semanticFields';
  import { fromApiField } from '../utils/semanticFieldRules';
  import Icon from './Icon.svelte';

  let {
    field,
    apiFields,
    onApply,
  }: {
    field: SemanticField;
    /** All fields in API shape, so the draft can follow the project's naming. */
    apiFields: unknown[];
    onApply: (field: SemanticField) => void;
  } = $props();

  let available = $state<boolean | null>(null);
  let unavailableReason = $state('');
  let open = $state(false);
  let description = $state('');
  let refineText = $state('');
  let loading = $state(false);
  let error = $state<string | null>(null);
  let result = $state<SemanticFieldDraft | null>(null);

  onMount(async () => {
    try {
      const status = await fetchAssistStatus();
      available = status.available;
      unavailableReason = status.reason ?? '';
    } catch {
      available = false;
      unavailableReason = 'Couldn’t reach the backend.';
    }
  });

  async function run(refine: boolean) {
    const text = refine ? refineText.trim() : description.trim();
    if (!text) return;
    loading = true;
    error = null;
    try {
      result = await draftSemanticField({
        description: text,
        field_name: field.name || null,
        field_id: field.id,
        existing_fields: apiFields,
        previous: refine && result ? result.draft : null,
      });
      refineText = '';
    } catch (err) {
      error = err instanceof Error ? err.message : 'Drafting failed.';
    } finally {
      loading = false;
    }
  }

  function apply() {
    if (!result) return;
    onApply(fromApiField(result.field));
    result = null;
    description = '';
    open = false;
  }

  const proposal = $derived(result ? fromApiField(result.field) : null);

  /** What Apply would change in the field as it is now. */
  const changes = $derived.by(() => {
    if (!proposal) return [];
    const list: string[] = [];
    if (proposal.name !== field.name) list.push(`Name: ${field.name || '(empty)'} → ${proposal.name}`);
    if (proposal.type !== field.type) {
      list.push(`Source: ${proposal.type === 'stochastic' ? 'sampled' : 'from GIS'}`);
    }
    const before = field.transformationRule?.sourceColumn;
    const after = proposal.transformationRule?.sourceColumn;
    if (after && after !== before) list.push(`GIS column: ${before || '(none)'} → ${after}`);
    const added = proposal.options.filter((o) => !field.options.includes(o));
    const removed = field.options.filter((o) => !proposal.options.includes(o));
    if (added.length) list.push(`Adds options: ${added.join(', ')}`);
    if (removed.length) list.push(`Removes options: ${removed.join(', ')}`);
    if (list.length === 0) list.push('Updates the rule details only.');
    return list;
  });
</script>

{#if available}
  <div class="assist" class:open>
    {#if !open}
      <button type="button" class="btn btn-link" onclick={() => (open = true)}>
        <Icon name="sparkle" size={14} />
        Describe this field in plain words and get a draft
      </button>
    {:else}
      <div class="assist-head">
        <h3><Icon name="sparkle" size={14} /> Draft with AI</h3>
        <button type="button" class="btn btn-ghost btn-sm" onclick={() => (open = false)} aria-label="Hide AI drafting">Hide</button>
      </div>

      {#if !result}
        <label class="describe">
          <span class="visually-hidden">Describe the field</span>
          <textarea
            rows="3"
            bind:value={description}
            placeholder="e.g. Age band from YEARBLT: before 1975, 1975 to 2003, and newer"
            onkeydown={(event) => (event.metaKey || event.ctrlKey) && event.key === 'Enter' && run(false)}
          ></textarea>
        </label>
        <div class="actions">
          <button type="button" class="btn" onclick={() => run(false)} disabled={loading || description.trim().length < 3}>
            {loading ? 'Drafting…' : 'Draft'}
          </button>
          <span class="hint privacy">Sends column names and sampled values (not whole rows) to Anthropic.</span>
        </div>
      {/if}

      {#if error}
        <p class="status-err msg" role="alert"><Icon name="x" size={14} /><span>{error}</span></p>
      {/if}

      {#if result && proposal}
        <div class="proposal" aria-live="polite">
          <div class="proposal-head">
            <strong>{proposal.name}</strong>
            <span class="tag">{proposal.type === 'stochastic' ? 'sampled' : `from ${proposal.transformationRule?.sourceColumn}`}</span>
            {#if result.coverage}
              <span class="coverage">{result.coverage.mapped_percent}% of buildings classified</span>
            {/if}
          </div>

          {#if proposal.transformationRule?.numericRanges?.length}
            <table class="data-table">
              <thead><tr><th>Option</th><th class="num">From</th><th class="num">To</th></tr></thead>
              <tbody>
                {#each proposal.transformationRule.numericRanges as range}
                  <tr><td>{range.label}</td><td class="num">{range.min}</td><td class="num">{range.max}</td></tr>
                {/each}
              </tbody>
            </table>
          {:else if proposal.transformationRule?.categoricalGroups?.length}
            <table class="data-table">
              <thead><tr><th>Option</th><th>Values in GIS</th></tr></thead>
              <tbody>
                {#each proposal.transformationRule.categoricalGroups as group}
                  <tr><td>{group.groupLabel}</td><td>{group.sourceValues.join(', ')}</td></tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="hint">Options: {proposal.options.join(', ')}</p>
          {/if}

          {#each result.errors as message}
            <p class="status-err msg"><Icon name="x" size={14} /><span>{message}</span></p>
          {/each}
          {#each result.warnings as message}
            <p class="status-warn msg"><Icon name="alert" size={14} /><span>{message}</span></p>
          {/each}

          {#if result.assumptions.length}
            <div class="notes">
              <h4>Assumed</h4>
              <ul>{#each result.assumptions as item}<li>{item}</li>{/each}</ul>
            </div>
          {/if}
          {#if result.questions.length}
            <div class="notes">
              <h4>Worth deciding</h4>
              <ul>{#each result.questions as item}<li>{item}</li>{/each}</ul>
            </div>
          {/if}

          <div class="notes">
            <h4>Apply will</h4>
            <ul>{#each changes as item}<li>{item}</li>{/each}</ul>
          </div>

          <div class="refine">
            <input
              type="text"
              bind:value={refineText}
              placeholder="Ask for a change, e.g. split the last band at 2015"
              onkeydown={(event) => event.key === 'Enter' && run(true)}
              aria-label="Requested change"
            />
            <button type="button" class="btn btn-secondary" onclick={() => run(true)} disabled={loading || !refineText.trim()}>
              {loading ? 'Revising…' : 'Revise'}
            </button>
          </div>

          <div class="actions">
            <button type="button" class="btn" onclick={apply} disabled={loading}>Apply to field</button>
            <button type="button" class="btn btn-secondary" onclick={() => (result = null)} disabled={loading}>Discard</button>
          </div>
        </div>
      {/if}
    {/if}
  </div>
{:else if available === false && unavailableReason}
  <p class="hint unavailable" title={unavailableReason}><Icon name="sparkle" size={12} /> AI drafting is off: {unavailableReason}</p>
{/if}

<style>
  .assist {
    padding: var(--space-3) var(--space-4);
    border: 1px dashed var(--accent-border);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--accent-soft) 60%, var(--surface));
    margin-bottom: var(--space-4);
  }

  .assist.open {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .assist-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h3 {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-md);
    font-weight: 600;
    color: var(--text);
  }

  h3 :global(.icon),
  .unavailable :global(.icon) {
    color: var(--accent);
  }

  h4 {
    margin-bottom: 2px;
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }

  textarea {
    width: 100%;
    resize: vertical;
  }

  .refine {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  .refine input {
    flex: 1;
    min-width: 200px;
  }

  .privacy,
  .unavailable {
    font-size: var(--text-xs);
  }

  .unavailable {
    margin-bottom: var(--space-3);
  }

  /* A tone step inside the dashed box, not a second frame. */
  .proposal {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .proposal-head {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    flex-wrap: wrap;
    font-size: var(--text-md);
  }

  .coverage {
    margin-left: auto;
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-2);
  }

  .data-table td {
    overflow-wrap: anywhere;
  }

  .msg {
    font-size: var(--text-xs);
  }

  .notes ul {
    padding-left: var(--space-4);
    font-size: var(--text-xs);
    color: var(--text-2);
  }
</style>
