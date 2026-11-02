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
      <button type="button" class="assist-toggle" onclick={() => (open = true)}>
        <span class="spark" aria-hidden="true">✦</span>
        Describe this field in plain words and get a draft
      </button>
    {:else}
      <div class="assist-head">
        <h3><span class="spark" aria-hidden="true">✦</span> Draft with AI</h3>
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
        <div class="row">
          <button type="button" class="btn" onclick={() => run(false)} disabled={loading || description.trim().length < 3}>
            {loading ? 'Drafting…' : 'Draft'}
          </button>
          <span class="privacy">Sends column names and sampled values (not whole rows) to Anthropic.</span>
        </div>
      {/if}

      {#if error}
        <p class="msg err" role="alert"><span aria-hidden="true">✕</span> {error}</p>
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
            <table>
              <thead><tr><th>Option</th><th>From</th><th>To</th></tr></thead>
              <tbody>
                {#each proposal.transformationRule.numericRanges as range}
                  <tr><td>{range.label}</td><td>{range.min}</td><td>{range.max}</td></tr>
                {/each}
              </tbody>
            </table>
          {:else if proposal.transformationRule?.categoricalGroups?.length}
            <table>
              <thead><tr><th>Option</th><th>Values in GIS</th></tr></thead>
              <tbody>
                {#each proposal.transformationRule.categoricalGroups as group}
                  <tr><td>{group.groupLabel}</td><td>{group.sourceValues.join(', ')}</td></tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="muted">Options: {proposal.options.join(', ')}</p>
          {/if}

          {#each result.errors as message}
            <p class="msg err"><span aria-hidden="true">✕</span> {message}</p>
          {/each}
          {#each result.warnings as message}
            <p class="msg warn"><span aria-hidden="true">!</span> {message}</p>
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

          <div class="row">
            <button type="button" class="btn" onclick={apply} disabled={loading}>Apply to field</button>
            <button type="button" class="btn btn-secondary" onclick={() => (result = null)} disabled={loading}>Discard</button>
          </div>
        </div>
      {/if}
    {/if}
  </div>
{:else if available === false && unavailableReason}
  <p class="unavailable" title={unavailableReason}>✦ AI drafting is off: {unavailableReason}</p>
{/if}

<style>
  .assist {
    border: 1px dashed var(--accent-border);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--accent-soft) 60%, var(--surface));
    margin-bottom: 16px;
  }

  .assist.open {
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .assist-toggle {
    width: 100%;
    padding: 10px 14px;
    border: none;
    background: transparent;
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    text-align: left;
    cursor: pointer;
  }

  .spark {
    color: var(--accent);
  }

  .assist-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h3 {
    margin: 0;
    font-size: 14px;
    color: var(--text);
  }

  h4 {
    margin: 0 0 2px;
    font-size: 12px;
    color: var(--text-muted);
  }

  textarea,
  .refine input {
    width: 100%;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    padding: 8px 10px;
    font: inherit;
    font-size: 13px;
    background: var(--surface);
    color: var(--text);
    resize: vertical;
  }

  .row,
  .refine {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .refine input {
    flex: 1;
    min-width: 200px;
  }

  .privacy,
  .muted,
  .unavailable {
    font-size: 12px;
    color: var(--text-muted);
  }

  .unavailable {
    margin-bottom: 12px;
  }

  .proposal {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .proposal-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 14px;
  }

  .tag {
    font-size: 11px;
    padding: 1px 8px;
    border-radius: var(--radius-sm);
    background: var(--surface-3);
    color: var(--text-2);
  }

  .coverage {
    margin-left: auto;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  th {
    text-align: left;
    color: var(--text-muted);
    font-weight: 600;
    padding: 4px 6px;
    border-bottom: 1px solid var(--border);
  }

  td {
    padding: 4px 6px;
    border-bottom: 1px solid var(--surface-3);
    color: var(--text);
    overflow-wrap: anywhere;
  }

  .msg {
    margin: 0;
    font-size: 12px;
    font-weight: 600;
  }

  .msg.err {
    color: var(--err-text);
  }

  .msg.warn {
    color: var(--warn-text);
  }

  .notes ul {
    margin: 0;
    padding-left: 18px;
    font-size: 12px;
    color: var(--text-2);
  }
</style>
