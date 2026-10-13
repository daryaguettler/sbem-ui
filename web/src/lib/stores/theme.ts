import { readable, writable } from 'svelte/store';

export type ThemeChoice = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'sbem-ui:theme';

function readSaved(): ThemeChoice {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // storage blocked: fall back to the OS setting
  }
  return 'system';
}

function apply(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === 'system') delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    if (choice === 'system') localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // not persisted, but still applied for this session
  }
}

/** The user's choice; 'system' follows prefers-color-scheme. index.html applies it before paint. */
export const themeChoice = writable<ThemeChoice>(readSaved());
themeChoice.subscribe(apply);

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
const systemDark = readable(darkQuery.matches, (set) => {
  const onChange = (event: MediaQueryListEvent) => set(event.matches);
  darkQuery.addEventListener('change', onChange);
  return () => darkQuery.removeEventListener('change', onChange);
});

/** The theme actually rendered, for code that can't use CSS variables (xyflow colorMode). */
export const resolvedTheme = readable<'light' | 'dark'>('light', (set) => {
  let choice: ThemeChoice = 'system';
  let osDark = darkQuery.matches;
  const update = () => set(choice === 'system' ? (osDark ? 'dark' : 'light') : choice);
  const unsubChoice = themeChoice.subscribe((value) => {
    choice = value;
    update();
  });
  const unsubOs = systemDark.subscribe((value) => {
    osDark = value;
    update();
  });
  return () => {
    unsubChoice();
    unsubOs();
  };
});
