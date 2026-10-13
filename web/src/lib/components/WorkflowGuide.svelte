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
    <button type="button" class="action" onclick={() => navigateTo(target)}>
      {actionLabel}
    </button>
  {/if}
</div>

<style>
  .guide {
    padding: 24px;
    border: 1px solid var(--accent-border);
    border-radius: 12px;
    background: var(--accent-soft);
  }

  .guide h2 {
    margin: 0 0 8px;
    font-size: 18px;
    color: var(--text);
  }

  .guide p {
    margin: 0 0 16px;
    color: var(--accent-hover);
    line-height: 1.5;
  }

  .action {
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: var(--on-accent);
    padding: 10px 16px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
  }
</style>
