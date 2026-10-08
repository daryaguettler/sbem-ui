<script lang="ts">
  import { navigateTo } from '../stores/projectStore';
  import type { WorkflowId } from '../types/workflow';

  export let title: string;
  export let message: string;
  export let actionLabel: string;
  export let actionWorkflow: WorkflowId;
</script>

<div class="guide">
  <h2>{title}</h2>
  <p>{message}</p>
  <button type="button" class="action" onclick={() => navigateTo(actionWorkflow)}>
    {actionLabel}
  </button>
</div>

<style>
  .guide {
    padding: 24px;
    border: 1px solid #dbeafe;
    border-radius: 12px;
    background: #eff6ff;
  }

  .guide h2 {
    margin: 0 0 8px;
    font-size: 18px;
    color: #1e3a8a;
  }

  .guide p {
    margin: 0 0 16px;
    color: #1d4ed8;
    line-height: 1.5;
  }

  .action {
    border: none;
    border-radius: 8px;
    background: #2563eb;
    color: #ffffff;
    padding: 10px 16px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
  }
</style>
