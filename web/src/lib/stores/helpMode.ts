import { writable } from 'svelte/store';

export type HelpMode = 'explain' | 'minimal';

const STORAGE_KEY = 'sbem-ui:help';

function readSaved(): HelpMode {
  try {
    if (localStorage.getItem(STORAGE_KEY) === 'explain') return 'explain';
  } catch {
    // storage blocked: fall back to the default
  }
  return 'minimal';
}

/** 'explain' shows how-to text under headings; 'minimal' folds it into ⓘ tooltips. */
export const helpMode = writable<HelpMode>(readSaved());
helpMode.subscribe((mode) => {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // not persisted, but still applied for this session
  }
});
