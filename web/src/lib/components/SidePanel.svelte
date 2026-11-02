<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon from './Icon.svelte';

  let {
    title,
    subtitle = '',
    onClose,
    children,
  }: {
    title: string;
    subtitle?: string;
    onClose: () => void;
    children: Snippet;
  } = $props();

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && !event.defaultPrevented) onClose();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<!-- A docked editor panel. The parent decides where it sits (a grid column, or an
     absolutely-positioned drawer on narrow screens); this only owns header + scrolling. -->
<aside class="side-panel" aria-label={title}>
  <header class="side-panel-header">
    <div class="titles">
      <h2>{title}</h2>
      {#if subtitle}<p>{subtitle}</p>{/if}
    </div>
    <button type="button" class="btn btn-ghost btn-sm" onclick={onClose} aria-label="Close panel" title="Close (Esc)">
      <Icon name="x" />
    </button>
  </header>
  <div class="side-panel-body">
    {@render children()}
  </div>
</aside>

<style>
  .side-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    background: var(--surface);
    border-left: 1px solid var(--border);
  }

  .side-panel-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid var(--border);
  }

  .titles {
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text);
    overflow-wrap: anywhere;
  }

  p {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  .side-panel-body {
    --panel-pad: var(--space-5);
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--space-4) var(--panel-pad) 0;
  }
</style>
