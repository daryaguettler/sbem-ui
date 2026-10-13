<script lang="ts">
  import { componentMapStore } from '../../stores/componentMapStore';
  import {
    buildComponentLevels,
    collectSelectors,
    getSelectorStatus,
  } from '../../utils/componentMapTree';

  const componentLevels = buildComponentLevels();

  $: selectors = $componentMapStore.map
    ? collectSelectors($componentMapStore.map)
    : [];

  function selectPath(path: string) {
    componentMapStore.setSelectedPath(path);
  }
</script>

{#if !$componentMapStore.map}
  <p class="empty">Load or create a component map to edit selectors.</p>
{:else}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Component path</th>
          <th>Status</th>
          <th>Source fields</th>
          <th>Suffix</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each componentLevels as level}
          {@const status = getSelectorStatus($componentMapStore.map!, level.path)}
          {@const selector = selectors.find((entry) => entry.path === level.path)}
          <tr class:selected={$componentMapStore.selectedPath === level.path}>
            <td>
              <span style={`padding-left:${level.depth * 16}px`}>{level.displayName}</span>
              <div class="path">{level.path}</div>
            </td>
            <td><span class="status {status}"><span aria-hidden="true">{status === 'mapped' ? '✓' : status === 'inherited' ? '↳' : '✕'}</span> {status}</span></td>
            <td>{selector?.source_fields.join(', ') || '—'}</td>
            <td>{selector?.suffix || '—'}</td>
            <td>
              <button type="button" class="link-btn" onclick={() => selectPath(level.path)}>Edit</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: 14px;
  }

  .table-wrap {
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th,
  td {
    border-bottom: 1px solid var(--border);
    padding: 10px 12px;
    text-align: left;
    vertical-align: top;
    color: var(--text);
  }

  tr.selected {
    background: var(--accent-soft);
  }

  .path {
    font-size: 11px;
    color: var(--text-faint);
    font-family: monospace;
    margin-top: 2px;
  }

  .status {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    text-transform: capitalize;
  }

  .status.mapped {
    background: var(--ok-bg);
    color: var(--ok-text);
  }

  .status.inherited {
    background: var(--accent-soft);
    color: var(--accent);
  }

  .status.unmapped {
    background: var(--err-bg);
    color: var(--err-text);
  }

  .link-btn {
    border: 1px solid var(--accent);
    background: var(--surface);
    color: var(--accent);
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    font-size: 12px;
  }
</style>
