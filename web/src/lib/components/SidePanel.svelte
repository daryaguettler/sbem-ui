<script lang="ts">
  import type { Snippet } from 'svelte';

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
    <button type="button" class="btn btn-ghost close" onclick={onClose} aria-label="Close panel" title="Close (Esc)">
      &times;
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
    gap: 12px;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
  }

  .titles {
    min-width: 0;
  }

  h2 {
    font-size: 16px;
    color: var(--text);
    overflow-wrap: anywhere;
  }

  p {
    font-size: 12px;
    color: var(--text-muted);
  }

  .close {
    font-size: 20px;
    line-height: 1;
    padding: 2px 8px;
  }

  .side-panel-body {
    --panel-pad: 20px;
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 16px var(--panel-pad) 0;
  }
</style>
