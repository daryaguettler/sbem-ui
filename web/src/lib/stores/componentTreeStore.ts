import { writable } from 'svelte/store';

export interface ComponentTreeNode {
  path: string;
  displayName: string;
  componentType: string | null;
  children: string[];
  isLeaf: boolean;
}

export interface ComponentTreeState {
  loaded: boolean;
  roots: string[];
  nodesByPath: Record<string, ComponentTreeNode>;
}

function createComponentTreeStore() {
  const { subscribe, set } = writable<ComponentTreeState>({
    loaded: false,
    roots: [],
    nodesByPath: {},
  });

  async function load() {
    let response: Response;
    try {
      response = await fetch('/api/component-tree/');
    } catch {
      // Backend unreachable -- leave the store in its unloaded state. The
      // workspace picker/App shell surfaces the "can't reach backend" message;
      // this store doesn't need to duplicate it.
      return;
    }
    if (!response.ok) return;
    const payload = (await response.json().catch(() => null)) as {
      roots: string[];
      nodes: ComponentTreeNode[];
    } | null;
    if (!payload) return;
    const nodesByPath: Record<string, ComponentTreeNode> = {};
    for (const node of payload.nodes) {
      nodesByPath[node.path] = node;
    }
    set({ loaded: true, roots: payload.roots, nodesByPath });
  }

  return { subscribe, load };
}

export const componentTreeStore = createComponentTreeStore();
