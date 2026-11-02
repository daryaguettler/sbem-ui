<script lang="ts">
  import { componentMapStore } from '../../stores/componentMapStore';
  import Icon from '../Icon.svelte';
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
  <p class="empty">No model parts are connected yet.</p>
{:else}
  <div class="data-table-wrap">
    <table class="data-table">
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
              <div style={`padding-left: calc(${level.depth} * var(--space-4))`}>
                {level.displayName}
                <div class="path">{level.path}</div>
              </div>
            </td>
            <td>
              <span class="tag status" class:tag-ok={status === 'mapped'} class:tag-err={status === 'unmapped'}>
                <Icon name={status === 'mapped' ? 'check' : status === 'inherited' ? 'corner-down-right' : 'x'} size={12} />{status}
              </span>
            </td>
            <td>{selector?.source_fields.join(', ') || '—'}</td>
            <td>{selector?.suffix || '—'}</td>
            <td>
              <button type="button" class="btn btn-secondary btn-sm" onclick={() => selectPath(level.path)}>Edit</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  tr.selected {
    background: var(--accent-soft);
  }

  .path {
    margin-top: var(--space-1);
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }

  .status {
    text-transform: capitalize;
  }
</style>
