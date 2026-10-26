<script module lang="ts">
  export interface SelectOption {
    value: string;
    label: string;
    disabled?: boolean;
    /** Options sharing a group are listed under that heading, in first-seen order. */
    group?: string;
  }
</script>

<script lang="ts">
  /**
   * The app's dropdown: a bits-ui Select styled like the other form controls.
   * Controlled -- it shows `value` and reports picks through `onChange`, so a parent that
   * doesn't store the pick (an "add…" menu) simply stays on its placeholder.
   * An option with value '' is a real choice ("Not mapped", "always"); a prompt nobody
   * should pick goes in `placeholder` instead.
   */
  import { Select } from 'bits-ui';

  let {
    value,
    options,
    onChange,
    placeholder = 'Select…',
    disabled = false,
    ariaLabel,
    title,
    id,
  }: {
    value: string;
    options: SelectOption[];
    onChange: (value: string) => void;
    placeholder?: string;
    disabled?: boolean;
    ariaLabel?: string;
    title?: string;
    id?: string;
  } = $props();

  const selectedLabel = $derived(options.find((option) => option.value === value)?.label);
  const groups = $derived.by(() => {
    const byHeading = new Map<string | undefined, SelectOption[]>();
    for (const option of options) {
      if (!byHeading.has(option.group)) byHeading.set(option.group, []);
      byHeading.get(option.group)!.push(option);
    }
    return [...byHeading.entries()].map(([heading, items]) => ({ heading, items }));
  });
</script>

{#snippet item(option: SelectOption)}
  <Select.Item class="ui-select-item" value={option.value} label={option.label} disabled={option.disabled}>
    {#snippet children({ selected })}
      <span class="ui-select-check" aria-hidden="true">{selected ? '✓' : ''}</span>
      {option.label}
    {/snippet}
  </Select.Item>
{/snippet}

<Select.Root type="single" {value} onValueChange={onChange} items={options} allowDeselect={false} {disabled}>
  <Select.Trigger class="ui-select-trigger" aria-label={ariaLabel} {title} {id}>
    <span class="ui-select-value" class:ui-select-placeholder={selectedLabel === undefined}>
      {selectedLabel ?? placeholder}
    </span>
    <span class="ui-select-chevron" aria-hidden="true">▾</span>
  </Select.Trigger>
  <Select.Portal>
    <Select.Content class="ui-select-content" sideOffset={4}>
      <Select.Viewport>
        {#each groups as group (group.heading ?? '')}
          {#if group.heading}
            <Select.Group>
              <Select.GroupHeading class="ui-select-heading">{group.heading}</Select.GroupHeading>
              {#each group.items as option (option.value)}{@render item(option)}{/each}
            </Select.Group>
          {:else}
            {#each group.items as option (option.value)}{@render item(option)}{/each}
          {/if}
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Portal>
</Select.Root>

<style>
  /* The list renders in a portal outside this component, so its styles are global,
     namespaced under ui-select-*. */
  :global(.ui-select-trigger) {
    display: inline-flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--control-h);
    padding: 0 var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: 400;
    text-align: left;
    cursor: pointer;
  }

  :global(.ui-select-trigger:disabled) {
    background: var(--surface-3);
    color: var(--text-muted);
    cursor: not-allowed;
  }

  :global(.ui-select-value) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global(.ui-select-placeholder) {
    color: var(--text-muted);
  }

  :global(.ui-select-chevron) {
    flex: none;
    color: var(--text-muted);
    font-size: 11px;
  }

  :global(.ui-select-content) {
    z-index: 50;
    min-width: var(--bits-floating-anchor-width);
    max-height: min(320px, var(--bits-floating-available-height));
    overflow-y: auto;
    padding: 4px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: var(--shadow-lg);
  }

  :global(.ui-select-item) {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    color: var(--text);
    cursor: pointer;
    user-select: none;
  }

  :global(.ui-select-item[data-highlighted]) {
    background: var(--accent-soft);
  }

  :global(.ui-select-item[data-disabled]) {
    color: var(--text-muted);
    cursor: not-allowed;
  }

  :global(.ui-select-check) {
    width: 1em;
    flex: none;
    color: var(--accent);
  }

  :global(.ui-select-heading) {
    padding: 6px 8px 2px;
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }
</style>
