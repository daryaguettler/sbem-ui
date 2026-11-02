<script lang="ts">
  import { navigateTo } from '../stores/projectStore';
  import type { WorkflowId } from '../types/workflow';

  export let title: string;
  export let message: string;
  /** Omit both to show the guide without a button (e.g. when the action is on this page). */
  export let actionLabel = '';
  export let actionWorkflow: WorkflowId | null = null;
</script>

<div class="guide">
  <h2>{title}</h2>
  <p>{message}</p>
  {#if actionLabel && actionWorkflow}
    {@const target = actionWorkflow}
    <button type="button" class="btn" onclick={() => navigateTo(target)}>
      {actionLabel}
    </button>
  {/if}
</div>

<style>
  .guide {
    padding: var(--space-5);
    border: 1px solid var(--accent-border);
    border-radius: var(--radius);
    background: var(--accent-soft);
  }

  .guide h2 {
    margin: 0 0 var(--space-1);
    font-size: var(--text-lg);
    color: var(--text);
  }

  .guide p {
    margin: 0 0 var(--space-3);
    font-size: var(--text-sm);
    color: var(--accent-hover);
    line-height: 1.5;
  }
</style>
