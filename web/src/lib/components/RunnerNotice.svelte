<script lang="ts">
  /** Shown on pages whose live features need the project's runner repo (project.json "runner"). */
  export let feature: string;
</script>

<div class="notice">
  <strong>No runner configured for this project.</strong>
  <p>
    {feature} needs a runner repo (currently norway-globi's <code>norway</code> CLI). Add
    <code>"runner": "&lt;path to the repo, relative to the project&gt;"</code> to this project's
    <code>project.json</code> and reopen the project.
  </p>
</div>

<style>
  .notice {
    border: 1px solid var(--warn-border);
    background: var(--warn-bg);
    border-radius: 12px;
    padding: 14px 18px;
    font-size: 13px;
    color: var(--warn-text);
  }

  .notice p {
    margin: 6px 0 0;
    line-height: 1.5;
  }

  code {
    font-size: 12px;
  }
</style>
