<script lang="ts">
  import { helpMode } from '../stores/helpMode';
  import HelpTip from './HelpTip.svelte';

  // Place the `tip` form inline in the heading and the plain form under it; each
  // renders only in its own mode, so a hint is either prose or an ⓘ, never both.
  let { text, tip = false }: { text: string; tip?: boolean } = $props();
</script>

{#if tip && $helpMode === 'minimal'}
  <HelpTip {text} />
{:else if !tip && $helpMode === 'explain'}
  <p class="explain">{text}</p>
{/if}
