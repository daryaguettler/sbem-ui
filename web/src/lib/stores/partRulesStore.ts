/** The project's part rules (part-rules.yaml) as the Component Map page edits them. */
import { writable } from 'svelte/store';
import type { CompileResult } from '../api/partRules';
import { emptyRule, type PartRule, type PartRules } from '../utils/partRules';

export interface PartRulesState {
  /** null: the project has no part rules (opened from an older project or a raw map). */
  rules: PartRules | null;
  /** The last compile, from the save that ran it. */
  compile: CompileResult | null;
  /** Rules are being read from an older project's component map. */
  converting: boolean;
}

function normalize(content: Record<string, unknown>): PartRules {
  const parts = (content.parts ?? {}) as Record<string, Partial<PartRule>>;
  return {
    assembly_base: (content.assembly_base as string | null | undefined) ?? null,
    parts: Object.fromEntries(
      Object.entries(parts).map(([path, rule]) => [path, { ...emptyRule(), ...rule, cells: rule.cells ?? {} }])
    ),
  };
}

function createPartRulesStore() {
  const { subscribe, set, update } = writable<PartRulesState>({ rules: null, compile: null, converting: false });
  return {
    subscribe,
    load: (content: Record<string, unknown>) => update((state) => ({ ...state, rules: normalize(content) })),
    setRules: (rules: PartRules | null) => update((state) => ({ ...state, rules })),
    setPart: (path: string, rule: PartRule) =>
      update((state) =>
        state.rules ? { ...state, rules: { ...state.rules, parts: { ...state.rules.parts, [path]: rule } } } : state
      ),
    setCompile: (compile: CompileResult | null) => update((state) => ({ ...state, compile })),
    setConverting: (converting: boolean) => update((state) => ({ ...state, converting })),
    reset: () => set({ rules: null, compile: null, converting: false }),
  };
}

export const partRulesStore = createPartRulesStore();
