import { get, writable } from 'svelte/store';

export interface WorkspaceStatus {
  path: string;
  name: string;
  createdAt: string | null;
  lastOpenedWorkflow: string | null;
}

export interface WorkspaceState {
  loading: boolean;
  open: boolean;
  workspace: WorkspaceStatus | null;
  error: string | null;
  /** True when the backend itself couldn't be reached (not open, not a validation error). */
  backendUnreachable: boolean;
}

const LAST_PATH_KEY = 'sbem-ui:last-workspace-path';
const UNREACHABLE_MESSAGE =
  'Cannot reach the backend at http://localhost:8000. Make sure it is running (see README: "Backend Setup").';

function rememberPath(path: string) {
  try {
    localStorage.setItem(LAST_PATH_KEY, path);
  } catch {
    // localStorage unavailable (private mode, etc.) -- not fatal, just skip auto-reopen.
  }
}

function recallPath(): string | null {
  try {
    return localStorage.getItem(LAST_PATH_KEY);
  } catch {
    return null;
  }
}

/** fetch() that never throws: network failures and non-JSON error bodies (e.g. the
 * dev proxy's own 500 page when the backend process isn't running at all) are
 * normalized into a `{ ok: false, unreachable: true }` result instead of an
 * uncaught rejection. */
async function safeFetchJson(
  input: string,
  init?: RequestInit
): Promise<{ ok: true; data: any } | { ok: false; unreachable: boolean; detail?: string }> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch {
    return { ok: false, unreachable: true };
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (data === null) {
      // Backend process isn't up at all -- Vite's proxy returns a non-JSON 500.
      return { ok: false, unreachable: true };
    }
    return { ok: false, unreachable: false, detail: data.detail };
  }

  const data = await response.json().catch(() => null);
  if (data === null) {
    return { ok: false, unreachable: true };
  }
  return { ok: true, data };
}

function createWorkspaceStore() {
  const store = writable<WorkspaceState>({
    loading: false,
    open: false,
    workspace: null,
    error: null,
    backendUnreachable: false,
  });
  const { subscribe, set, update } = store;

  async function refreshStatus() {
    const result = await safeFetchJson('/api/workspace/status');
    if (!result.ok) {
      set({
        loading: false,
        open: false,
        workspace: null,
        error: result.unreachable ? UNREACHABLE_MESSAGE : result.detail ?? 'Failed to load workspace status.',
        backendUnreachable: result.unreachable,
      });
      return false;
    }
    set({
      loading: false,
      open: result.data.open,
      workspace: result.data.workspace,
      error: null,
      backendUnreachable: false,
    });
    return result.data.open as boolean;
  }

  async function create(path: string, name: string) {
    update((state) => ({ ...state, loading: true, error: null }));
    const result = await safeFetchJson('/api/workspace/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, name }),
    });
    if (!result.ok) {
      const message = result.unreachable ? UNREACHABLE_MESSAGE : result.detail ?? 'Failed to create project workspace.';
      update((state) => ({ ...state, loading: false, error: message, backendUnreachable: result.unreachable }));
      return false;
    }
    const workspace = result.data as WorkspaceStatus;
    rememberPath(workspace.path);
    set({ loading: false, open: true, workspace, error: null, backendUnreachable: false });
    return true;
  }

  async function open(path: string) {
    update((state) => ({ ...state, loading: true, error: null }));
    const result = await safeFetchJson('/api/workspace/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    if (!result.ok) {
      const message = result.unreachable ? UNREACHABLE_MESSAGE : result.detail ?? 'Failed to open project workspace.';
      update((state) => ({ ...state, loading: false, error: message, backendUnreachable: result.unreachable }));
      return false;
    }
    const workspace = result.data as WorkspaceStatus;
    rememberPath(workspace.path);
    set({ loading: false, open: true, workspace, error: null, backendUnreachable: false });
    return true;
  }

  async function close() {
    await safeFetchJson('/api/workspace/close', { method: 'POST' });
    set({ loading: false, open: false, workspace: null, error: null, backendUnreachable: false });
  }

  async function tryReopenLastWorkspace() {
    const alreadyOpen = await refreshStatus();
    if (alreadyOpen) return true;
    if (get(store).backendUnreachable) return false;

    const lastPath = recallPath();
    if (!lastPath) return false;
    return open(lastPath);
  }

  return { subscribe, create, open, close, refreshStatus, tryReopenLastWorkspace };
}

export const workspaceStore = createWorkspaceStore();
