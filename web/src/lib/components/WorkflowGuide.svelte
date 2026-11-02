<script lang="ts">
  import { navigateTo } from '../stores/projectStore';
  import type { WorkflowId } from '../types/workflow';

  export let title: string;
  export let message: string;
  /** Omit both to show the guide without a button (e.g. when the action is on this page). */
  export let actionLabel = '';
  export let actionWorkflow: WorkflowId | null = null;
</script>

<div class="panel guide">
  <h2>{title}</h2>
  <p>{message}</p>
  {#if actionLabel && actionWorkflow}
    {@const target = actionWorkflow}
    <div class="actions">
      <button type="button" class="btn" onclick={() => navigateTo(target)}>
        {actionLabel}
      </button>
    </div>
  {/if}
</div>

<style>
  .guide {
    gap: var(--space-2);
    background: var(--surface-2);
  }

  .guide p {
    margin: 0;
    max-width: 72ch;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
</style>
