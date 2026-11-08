<script lang="ts">
  /**
   * Links between uncertain parts: each link lists parts whose variants move together (one
   * shared draw) or are correlated (drawn jointly). Collapsed to one line until opened; shown
   * only once two parts are uncertain or a link exists.
   */
  import Explain from '../Explain.svelte';
  import Icon from '../Icon.svelte';
  import { componentPriorsStore } from '../../stores/componentPriorsStore';
  import type { PartLink } from '../../utils/componentPriors';
  import { HELP } from '../../help';
  const help = HELP.componentPriors;

  let { parts }: { parts: Array<{ path: string; label: string }> } = $props();

  let open = $state(false);
  const links = $derived($componentPriorsStore.links ?? []);
  const uncertain = $derived(new Set(parts.map((part) => part.path)));
  const labelOf = (path: string) => parts.find((part) => part.path === path)?.label ?? path.split('.').pop();
  /** Parts no link has yet. */
  const free = $derived(parts.filter((part) => !links.some((link) => link.parts.includes(part.path))));

  function toggle(index: number, path: string) {
    const link = links[index];
    const next = link.parts.includes(path) ? link.parts.filter((p) => p !== path) : [...link.parts, path];
    componentPriorsStore.setLink(index, next.length ? { ...link, parts: next } : null);
  }

  function add() {
    componentPriorsStore.setLink(links.length, { parts: free.slice(0, 2).map((part) => part.path), link: 'together' });
    open = true;
  }

  const set = (index: number, link: PartLink) => componentPriorsStore.setLink(index, link);
  const summary = (link: PartLink) =>
    `${link.parts.map(labelOf).join(' + ')} ${link.link === 'together' ? 'move together' : `correlated (ρ ${link.link})`}`;
</script>

{#if parts.length >= 2 || links.length > 0}
  <section class="linked">
    <div class="head">
      <button type="button" class="opener" aria-expanded={open} onclick={() => (open = !open)}>
        <Icon name="bell-curve" size={14} />
        <strong>Linked uncertainty</strong>
        <span class="hint">{links.length ? links.map(summary).join('; ') : `${parts.length} uncertain parts, each drawn on its own`}</span>
        <Icon name={open ? 'chevron-down' : 'chevron-right'} size={14} />
      </button>
      <Explain text={help.links} tip />
    </div>

    {#if open}
      <Explain text={help.links} />
      <ul class="links">
        {#each links as link, index (index)}
          <li>
            <div class="chips" role="group" aria-label="Parts in this link">
              {#each [...parts.map((part) => part.path), ...link.parts.filter((p) => !uncertain.has(p))] as path (path)}
                {@const taken = !link.parts.includes(path) && links.some((other, i) => i !== index && other.parts.includes(path))}
                <button type="button" class="chip" class:on={link.parts.includes(path)} class:stale={!uncertain.has(path)} disabled={taken}
                  aria-pressed={link.parts.includes(path)} title={!uncertain.has(path) ? 'No longer uncertain: it is left out' : taken ? 'In another link' : ''}
                  onclick={() => toggle(index, path)}>{labelOf(path)}</button>
              {/each}
            </div>
            <div class="how">
              <div class="toggle" role="radiogroup" aria-label="How they move">
                <button type="button" role="radio" aria-checked={link.link === 'together'} class:selected={link.link === 'together'} onclick={() => set(index, { ...link, link: 'together' })}>move together</button>
                <button type="button" role="radio" aria-checked={typeof link.link === 'number'} class:selected={typeof link.link === 'number'} onclick={() => set(index, { ...link, link: 0.5 })}>are correlated</button>
              </div>
              {#if typeof link.link === 'number'}
                <label class="rho">ρ <input type="number" min="-0.95" max="0.95" step="0.05" value={link.link} aria-label="Correlation"
                  onchange={(e) => set(index, { ...link, link: Math.max(-0.95, Math.min(0.95, Number((e.currentTarget as HTMLInputElement).value) || 0)) })} /></label>
              {/if}
              <button type="button" class="btn btn-ghost btn-sm" aria-label="Remove this link" onclick={() => componentPriorsStore.setLink(index, null)}><Icon name="x" size={14} /></button>
            </div>
            {#if link.parts.filter((p) => uncertain.has(p)).length < 2}<p class="hint">Pick at least two parts.</p>{/if}
          </li>
        {/each}
      </ul>
      {#if free.length >= 2}
        <button type="button" class="btn btn-secondary btn-sm add" onclick={add}><Icon name="plus" size={14} />Link parts</button>
      {/if}
    {/if}
  </section>
{/if}

<style>
  .linked { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--space-2) var(--space-3); display: flex; flex-direction: column; gap: var(--space-2); }
  .head { display: flex; align-items: center; gap: var(--space-2); }
  .opener { display: inline-flex; align-items: center; gap: var(--space-2); border: none; background: none; padding: 0; cursor: pointer; color: var(--text); font-size: var(--text-sm); text-align: left; min-width: 0; }
  .opener .hint { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .links { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .links li { display: flex; flex-direction: column; gap: var(--space-1); padding-bottom: var(--space-2); border-bottom: 1px solid var(--border); }
  .chips { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .chip { min-height: 24px; border: 1px solid var(--border-strong); background: var(--surface); color: var(--text-2); border-radius: var(--radius-sm); padding: 0 var(--space-2); font-size: var(--text-xs); cursor: pointer; }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  .chip.stale { text-decoration: line-through; }
  .chip:disabled { opacity: 0.4; cursor: default; }
  .how { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); }
  .toggle { display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); overflow: hidden; }
  .toggle button { min-height: var(--control-h-sm); padding: 0 var(--space-2); border: none; background: var(--surface); color: var(--text-2); font-size: var(--text-xs); cursor: pointer; }
  .toggle button + button { border-left: 1px solid var(--border-strong); }
  .toggle button.selected { background: var(--accent-soft); color: var(--text); font-weight: 600; }
  .rho { display: inline-flex; align-items: center; gap: 4px; }
  .rho input { width: 70px; }
  .add { align-self: flex-start; }
</style>
