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
            <td><span class="status {status}">{status}</span></td>
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
    color: #6b7280;
    font-size: 14px;
  }

  .table-wrap {
    overflow: auto;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th,
  td {
    border-bottom: 1px solid #e5e7eb;
    padding: 10px 12px;
    text-align: left;
    vertical-align: top;
    color: #111827;
  }

  tr.selected {
    background: #eff6ff;
  }

  .path {
    font-size: 11px;
    color: #9ca3af;
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
    background: #dcfce7;
    color: #166534;
  }

  .status.inherited {
    background: #ffedd5;
    color: #c2410c;
  }

  .status.unmapped {
    background: #fee2e2;
    color: #b91c1c;
  }

  .link-btn {
    border: 1px solid #2563eb;
    background: #ffffff;
    color: #2563eb;
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    font-size: 12px;
  }
</style>
