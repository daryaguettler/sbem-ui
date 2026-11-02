<script lang="ts">
  /** The tutorial's step card, docked bottom-right, plus the outline on the boxes the step is about. */
  import { currentWorkflow, navigateTo } from '../stores/projectStore';
  import { workspaceStore } from '../stores/workspaceStore';
  import { TUTORIAL_STEPS, goToStep, tutorialDone, tutorialOn, tutorialSnapshot, tutorialStep } from '../stores/tutorial';
  import Icon from './Icon.svelte';

  const index = $derived(Math.min($tutorialStep, TUTORIAL_STEPS.length - 1));
  const step = $derived(TUTORIAL_STEPS[index]);
  const done = $derived($tutorialDone[index]);
  const why = $derived(done ? '' : (step.why?.($tutorialSnapshot) ?? ''));
  const last = $derived(index === TUTORIAL_STEPS.length - 1);
  const offPage = $derived($workspaceStore.open && step.workflow !== null && step.workflow !== $currentWorkflow);

  // Targets may mount later (page switch, a panel that appears after upload), so keep
  // looking for them while the step is open.
  // shortcut: an outline can be clipped by an overflow:hidden parent; switch to a top-layer overlay if a target turns out clipped.
  $effect(() => {
    const selector = step.targets.map((target) => `[data-tour="${target}"]`).join(', ');
    let marked: Element[] = [];
    let scrolled = false;
    const mark = () => {
      const found = [...document.querySelectorAll(selector)];
      if (found.length === marked.length && found.every((el, i) => el === marked[i])) return;
      marked.forEach((el) => el.classList.remove('tour-target'));
      found.forEach((el) => el.classList.add('tour-target'));
      marked = found;
      if (found[0] && !scrolled) {
        found[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
        scrolled = true;
      }
    };
    mark();
    const observer = new MutationObserver(mark);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      marked.forEach((el) => el.classList.remove('tour-target'));
    };
  });
</script>

<div class="tutorial" role="region" aria-label="Tutorial">
  <div class="top">
    <span class="hint">Step {index + 1} of {TUTORIAL_STEPS.length}</span>
    {#if step.done}
      <span class="tag {done ? 'tag-ok' : 'tag-warn'}">
        <Icon name={done ? 'check' : 'alert'} size={12} />{done ? 'Done' : 'To do'}
      </span>
    {/if}
    <button type="button" class="btn btn-ghost btn-sm close" title="Exit tutorial" aria-label="Exit tutorial" onclick={() => tutorialOn.set(false)}>
      <Icon name="x" />
    </button>
  </div>
  <h2 aria-live="polite">{step.title}</h2>
  <p>{step.body}</p>
  {#if why}<p class="why" role="status">{why}</p>{/if}
  <div class="actions">
    {#if offPage && step.workflow}
      {@const target = step.workflow}
      <button type="button" class="btn btn-link" onclick={() => navigateTo(target)}>Go there</button>
    {/if}
    <span class="spacer"></span>
    <button type="button" class="btn btn-secondary btn-sm" onclick={() => goToStep(index - 1)} disabled={index === 0}>Back</button>
    {#if last}
      <button type="button" class="btn btn-sm" class:btn-secondary={step.done && !done} onclick={() => tutorialOn.set(false)}>Finish</button>
    {:else}
      <button type="button" class="btn btn-sm" class:btn-secondary={step.done && !done} onclick={() => goToStep(index + 1)}>Next</button>
    {/if}
  </div>
</div>

<style>
  .tutorial {
    position: fixed;
    right: var(--space-5);
    bottom: var(--space-5);
    z-index: 50;
    width: min(340px, calc(100vw - 2 * var(--space-5)));
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: var(--shadow-lg);
  }

  .top {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .close {
    margin-left: auto;
  }

  h2 {
    margin: 0;
    font-size: var(--text-md);
    font-weight: 600;
    color: var(--text);
  }

  p {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-2);
  }

  .why {
    padding: var(--space-2);
    border-radius: var(--radius-sm);
    background: var(--warn-bg);
    color: var(--warn-text);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .spacer {
    flex: 1;
  }
</style>
