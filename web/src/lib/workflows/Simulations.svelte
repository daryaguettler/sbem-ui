<script lang="ts">
  /** globi's Hatchet dashboard (runs, workers, task logs), served by its local stack (`make engine`). */
  import { HATCHET_URL } from '../api/globiFiles';
</script>

<section class="workflow">
  <div class="workflow-header">
    <h1>Simulations</h1>
    <p class="hint">
      GloBI's Hatchet dashboard. <strong>Runs</strong> lists each batch, with one task per building; click a task for its
      logs. <strong>Workers</strong> should list the simulation and fan-out workers. Sign in with
      <code>admin@example.com</code> / <code>Admin123!!</code> (globi's local default). Needs <code>make engine</code> in the
      globi folder.
      <a href={HATCHET_URL} target="_blank" rel="noopener noreferrer">Open in a new tab</a>
    </p>
  </div>
  <iframe title="Hatchet dashboard" src={HATCHET_URL}></iframe>
</section>

<style>
  iframe {
    flex: 1;
    width: 100%;
    min-height: 75vh;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }
</style>
