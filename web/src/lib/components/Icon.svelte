<script lang="ts" module>
  // Outline icons on a 24-unit grid; path data from Lucide (ISC licence, lucide.dev).
  const PATHS = {
    check: ['M20 6 9 17l-5-5'],
    x: ['M18 6 6 18', 'm6 6 12 12'],
    alert: ['M2 12a10 10 0 1 0 20 0a10 10 0 1 0-20 0', 'M12 8v4', 'M12 16h.01'],
    'chevron-down': ['m6 9 6 6 6-6'],
    'chevron-left': ['m15 18-6-6 6-6'],
    'chevron-right': ['m9 18 6-6-6-6'],
    'arrow-up': ['m5 12 7-7 7 7', 'M12 19V5'],
    'arrow-down': ['M12 5v14', 'm19 12-7 7-7-7'],
    'arrow-left': ['m12 19-7-7 7-7', 'M19 12H5'],
    'arrow-right': ['M5 12h14', 'm12 5 7 7-7 7'],
    'corner-down-right': ['m15 10 5 5-5 5', 'M4 4v7a4 4 0 0 0 4 4h12'],
    plus: ['M5 12h14', 'M12 5v14'],
    minus: ['M5 12h14'],
    sparkle: [
      'M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z',
    ],
    file: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z', 'M14 2v4a2 2 0 0 0 2 2h4'],
    home: [
      'M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8',
      'M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
    ],
    grid: ['M3 3h7v7H3z', 'M14 3h7v7h-7z', 'M14 14h7v7h-7z', 'M3 14h7v7H3z'],
  } as const;

  export type IconName = keyof typeof PATHS;
</script>

<script lang="ts">
  // Decorative by default; pass `label` when the icon is the only content of a control.
  let { name, size = 16, label }: { name: IconName; size?: number; label?: string } = $props();
</script>

<svg
  class="icon"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden={label ? undefined : 'true'}
  aria-label={label}
  role={label ? 'img' : undefined}
>
  {#each PATHS[name] as d}
    <path {d} />
  {/each}
</svg>

<style>
  .icon {
    flex: none;
    vertical-align: -0.125em;
  }
</style>
