/** The project's component priors (component-priors.yaml): optional curves on component values. */
import { writable } from 'svelte/store';
import { withLink, withPrior, type ComponentPrior, type ComponentPriorsDoc, type PartLink } from '../utils/componentPriors';

const empty = (): ComponentPriorsDoc => ({ components: {} });

function createComponentPriorsStore() {
  const { subscribe, set, update } = writable<ComponentPriorsDoc>(empty());
  return {
    subscribe,
    load: (content: Record<string, unknown>) =>
      set({
        ...content,
        components: (content.components as ComponentPriorsDoc['components']) ?? {},
        links: (content.links as PartLink[]) ?? [],
      }),
    setPrior: (type: string, name: string, prior: ComponentPrior | null) => update((doc) => withPrior(doc, type, name, prior)),
    setLink: (index: number, link: PartLink | null) => update((doc) => withLink(doc, index, link)),
    reset: () => set(empty()),
  };
}

export const componentPriorsStore = createComponentPriorsStore();
