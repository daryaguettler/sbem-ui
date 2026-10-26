/**
 * The prior tree being edited.
 *
 * State is the `RegionConfig` document itself rather than a UI-shaped mirror of
 * it, so what the editor holds, what gets validated, what gets sampled, and what
 * lands in priors/priors.yaml are all the same object. A target's prior lives in
 * exactly one of two places -- `priors[target]` when it has no conditions,
 * `joints[]` when it does -- and `setPrior`/`setJoint` move it between them.
 */

import { writable } from 'svelte/store';
import {
  isConditionalPrior,
  type DependencyGraph,
  type Distribution,
  type JointSpec,
  type PriorConfig,
  type PriorSpec,
  type PriorTreesState,
  type PriorValidation,
  type RegistryField,
  type SampleSummary,
  type UnconditionalPriorSpec,
} from '../types/priorTrees';

/** Prefix the sampling engine gives the join keys it generates. */
export const COMPOUND_PREFIX = 'compound.';

export function emptyConfig(): PriorConfig {
  return { registry: { fields: [] }, priors: {}, joints: [], scenarios: [] };
}

const initialState: PriorTreesState = {
  config: emptyConfig(),
  selectedTemplate: null,
  selectedTarget: null,
  valid: false,
  validationErrors: [],
  validationWarnings: [],
  dependencies: { nodes: [], edges: [] },
  sample: null,
};

/**
 * Keep only the four config sections, dropping the `Name`/`description` keys the
 * template picker uses. They're harmless to the sampler, but leaving them in
 * would round-trip them into the project's saved priors.yaml.
 */
export function normalizeConfig(
  raw: Record<string, unknown> | PriorConfig | null | undefined
): PriorConfig {
  const source = (raw || {}) as Partial<PriorConfig>;
  const fields = source.registry?.fields;
  return {
    registry: { fields: Array.isArray(fields) ? fields : [] },
    priors: (source.priors && typeof source.priors === 'object' ? source.priors : {}) as PriorConfig['priors'],
    joints: Array.isArray(source.joints) ? source.joints : [],
    scenarios: Array.isArray(source.scenarios) ? source.scenarios : [],
  };
}

/** Every field that has a prior, whether conditioned or not. Compound keys are
 * machinery the generator adds, not targets, so they're left out. */
export function priorTargets(config: PriorConfig): string[] {
  return [
    ...Object.keys(config.priors).filter((name) => !name.startsWith(COMPOUND_PREFIX)),
    ...config.joints.map((joint) => joint.target),
  ];
}

/**
 * Drop compound-key priors nothing dispatches on any more.
 *
 * A conditioned numeric prior stores its join key in `priors`; when that prior is
 * removed or re-conditioned, the old key would otherwise linger and get sampled
 * into every result for no reason.
 */
function pruneCompoundKeys(config: PriorConfig): PriorConfig {
  const inUse = new Set(
    Object.values(config.priors)
      .map((prior) => (isConditionalPrior(prior) ? prior.source_feature : null))
      .filter((source): source is string => Boolean(source))
  );
  const priors = Object.fromEntries(
    Object.entries(config.priors).filter(
      ([name]) => !name.startsWith(COMPOUND_PREFIX) || inUse.has(name)
    )
  );
  return { ...config, priors };
}

export function jointFor(config: PriorConfig, target: string): JointSpec | null {
  return config.joints.find((joint) => joint.target === target) ?? null;
}

/** Drop any existing prior for `target` from both places it could live. */
function withoutTarget(config: PriorConfig, target: string): PriorConfig {
  const { [target]: _removed, ...priors } = config.priors;
  return pruneCompoundKeys({
    ...config,
    priors,
    joints: config.joints.filter((joint) => joint.target !== target),
  });
}

/** Editing a prior invalidates whatever the last validate/sample run concluded. */
function touched(state: PriorTreesState, config: PriorConfig): PriorTreesState {
  return {
    ...state,
    config,
    valid: false,
    validationErrors: [],
    validationWarnings: [],
    sample: null,
    };
}

const { subscribe, set, update } = writable<PriorTreesState>(initialState);

export const priorTreesStore = {
  subscribe,
  set,
  update,

  loadFromTemplate: (templateData: Record<string, unknown>, templateName: string) => {
    const config = normalizeConfig(templateData);
    update((state) => ({
      ...touched(state, config),
      selectedTemplate: templateName,
      selectedTarget: priorTargets(config)[0] ?? null,
      dependencies: { nodes: [], edges: [] },
    }));
  },

  startFromScratch: () => {
    update((state) => ({
      ...touched(state, emptyConfig()),
      selectedTemplate: null,
      selectedTarget: null,
      dependencies: { nodes: [], edges: [] },
    }));
  },

  setConfig: (config: PriorConfig) => {
    update((state) => touched(state, normalizeConfig(config)));
  },

  setSelectedTarget: (selectedTarget: string | null) => {
    update((state) => ({ ...state, selectedTarget }));
  },

  /** Store an unconditional prior for `target`, replacing any conditioned one. */
  setPrior: (target: string, prior: UnconditionalPriorSpec) => {
    update((state) => {
      const base = withoutTarget(state.config, target);
      return touched(state, { ...base, priors: { ...base.priors, [target]: prior } });
    });
  },

  /**
   * Apply a generated prior's `priors` entries for `target`, replacing whatever it
   * had. For a conditioned numeric prior this writes both the compound key and the
   * target's conditional prior in one go.
   */
  setPriorEntries: (target: string, entries: Record<string, PriorSpec>) => {
    update((state) => {
      const base = withoutTarget(state.config, target);
      return touched(state, pruneCompoundKeys({ ...base, priors: { ...base.priors, ...entries } }));
    });
  },

  /** Replace one branch of a conditioned numeric prior. */
  setConditionSampler: (target: string, matchVal: string, sampler: Record<string, unknown>) => {
    update((state) => {
      const prior = state.config.priors[target];
      if (!isConditionalPrior(prior)) return state;
      const conditions = prior.conditions.map((condition) =>
        condition.match_val === matchVal ? { ...condition, sampler } : condition
      );
      return touched(state, {
        ...state.config,
        priors: { ...state.config.priors, [target]: { ...prior, conditions } },
      });
    });
  },

  setConditionFallback: (target: string, sampler: Record<string, unknown>) => {
    update((state) => {
      const prior = state.config.priors[target];
      if (!isConditionalPrior(prior)) return state;
      return touched(state, {
        ...state.config,
        priors: { ...state.config.priors, [target]: { ...prior, fallback_prior: sampler } },
      });
    });
  },

  removeCondition: (target: string, matchVal: string) => {
    update((state) => {
      const prior = state.config.priors[target];
      if (!isConditionalPrior(prior)) return state;
      const conditions = prior.conditions.filter((condition) => condition.match_val !== matchVal);
      return touched(state, {
        ...state.config,
        priors: { ...state.config.priors, [target]: { ...prior, conditions } },
      });
    });
  },

  /** Store a conditioned prior for `target`, replacing any unconditional one. */
  setJoint: (joint: JointSpec) => {
    update((state) => {
      const base = withoutTarget(state.config, joint.target);
      return touched(state, { ...base, joints: [...base.joints, joint] });
    });
  },

  removeTarget: (target: string) => {
    update((state) => {
      const config = withoutTarget(state.config, target);
      return {
        ...touched(state, config),
        selectedTarget: state.selectedTarget === target ? priorTargets(config)[0] ?? null : state.selectedTarget,
      };
    });
  },

  /**
   * Replace one row of a joint's lookup table. Weights are stored exactly as the
   * user typed them; the sampler renormalizes, and the editor shows the running
   * total so an unintended 0.9 is visible rather than silently rescaled.
   */
  setTableRow: (target: string, key: string, weights: Distribution) => {
    update((state) => {
      const joints = state.config.joints.map((joint) =>
        joint.target === target ? { ...joint, table: { ...joint.table, [key]: weights } } : joint
      );
      return touched(state, { ...state.config, joints });
    });
  },

  setFallback: (target: string, fallback: Distribution) => {
    update((state) => {
      const joints = state.config.joints.map((joint) =>
        joint.target === target ? { ...joint, fallback } : joint
      );
      return touched(state, { ...state.config, joints });
    });
  },

  removeTableRow: (target: string, key: string) => {
    update((state) => {
      const joints = state.config.joints.map((joint) => {
        if (joint.target !== target) return joint;
        const { [key]: _removed, ...table } = joint.table;
        return { ...joint, table };
      });
      return touched(state, { ...state.config, joints });
    });
  },

  /** Add or replace registry entries, keeping the declared order stable. */
  mergeRegistryFields: (fields: RegistryField[]) => {
    update((state) => {
      if (fields.length === 0) return state;
      const byName = new Map(state.config.registry.fields.map((field) => [field.name, field]));
      for (const field of fields) byName.set(field.name, field);
      return touched(state, {
        ...state.config,
        registry: { fields: [...byName.values()] },
      });
    });
  },

  setRegistryField: (field: RegistryField) => {
    update((state) => {
      const exists = state.config.registry.fields.some((entry) => entry.name === field.name);
      const fields = exists
        ? state.config.registry.fields.map((entry) => (entry.name === field.name ? field : entry))
        : [...state.config.registry.fields, field];
      return touched(state, { ...state.config, registry: { fields } });
    });
  },

  setValidation: (validation: PriorValidation) => {
    update((state) => ({
      ...state,
      valid: validation.valid,
      validationErrors: validation.errors,
      validationWarnings: validation.warnings ?? [],
      dependencies: validation.dependencies ?? { nodes: [], edges: [] },
    }));
  },

  setDependencies: (dependencies: DependencyGraph) => {
    update((state) => ({ ...state, dependencies }));
  },

  setSample: (sample: SampleSummary | null) => {
    update((state) => ({ ...state, sample }));
  },

  reset: () => set({ ...initialState, config: emptyConfig() }),
};
