<script lang="ts">
  let { text, label = 'More info' }: { text: string; label?: string } = $props();

  const id = $props.id();
  let trigger = $state<HTMLButtonElement | null>(null);
  let bubble = $state<HTMLDivElement | null>(null);

  // The bubble lives in the top layer (popover="manual"), so scrolling panels can't
  // clip it; we place it next to the trigger ourselves, flipping above or below and
  // clamping to the viewport so it never lands in a corner.
  function show() {
    if (!trigger || !bubble) return;
    bubble.showPopover();
    const anchor = trigger.getBoundingClientRect();
    const box = bubble.getBoundingClientRect();
    const gap = 6;
    const below = anchor.bottom + gap + box.height <= window.innerHeight;
    const top = below ? anchor.bottom + gap : Math.max(8, anchor.top - gap - box.height);
    const left = Math.min(Math.max(8, anchor.left + anchor.width / 2 - box.width / 2), window.innerWidth - box.width - 8);
    bubble.style.top = `${top}px`;
    bubble.style.left = `${left}px`;
  }

  function hide() {
    if (bubble?.matches(':popover-open')) bubble.hidePopover();
  }
</script>

<button
  bind:this={trigger}
  type="button"
  class="help-tip"
  aria-label={label}
  aria-describedby={id}
  onmouseenter={show}
  onmouseleave={hide}
  onfocus={show}
  onblur={hide}
  onkeydown={(event) => event.key === 'Escape' && hide()}
>
  <span aria-hidden="true">i</span>
</button>
<div bind:this={bubble} {id} role="tooltip" popover="manual" class="help-bubble">{text}</div>

<style>
  .help-tip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    margin-left: 4px;
    border: 1px solid var(--border-strong);
    border-radius: 50%;
    background: var(--surface);
    color: var(--text-muted);
    font: italic 600 10px/1 Georgia, serif;
    vertical-align: middle;
    cursor: help;
    flex: none;
  }

  .help-tip:hover,
  .help-tip:focus-visible {
    border-color: var(--accent);
    color: var(--accent);
  }

  .help-bubble {
    position: fixed;
    inset: auto;
    margin: 0;
    max-width: 280px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text-2);
    box-shadow: var(--shadow-lg);
    font-size: 12px;
    font-weight: 400;
    font-style: normal;
    line-height: 1.45;
    text-align: left;
    white-space: normal;
  }
</style>
