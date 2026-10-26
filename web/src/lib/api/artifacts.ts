/**
 * Saving editor state into the open project on disk, reading it back, and browsing the
 * project directory. The payloads sent here are the same ones the "Export YAML" buttons
 * POST -- saving writes that document into the project instead of downloading it.
 */

export type ArtifactKind = 'semantic-fields' | 'component-map' | 'priors' | 'retrofits';

export interface ArtifactStatus {
  kind: ArtifactKind;
  label: string;
  description: string;
  path: string;
  exists: boolean;
  savedAt: string | null;
  /** The file globi reads (for the component map, the pruned component-map.yaml). */
  globiPath: string;
}

export interface SavedArtifact {
  kind: ArtifactKind;
  label: string;
  path: string;
  exists: boolean;
  savedAt: string | null;
  content: Record<string, unknown> | null;
}

export interface WorkspaceFile {
  path: string;
  name: string;
  size: number;
  modifiedAt: string | null;
  /** False for binaries (components-lib.db) -- listed, but there's nothing to show. */
  viewable: boolean;
  /** Set when this file is one of the saveable artifacts, so it can be loaded back in. */
  kind: ArtifactKind | null;
  label: string | null;
}

export interface WorkspaceFileContent extends WorkspaceFile {
  content: string | null;
  truncated: boolean;
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail ?? `Request to ${input} failed (${response.status}).`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json() as Promise<T>;
}

export async function fetchArtifactStatuses(): Promise<ArtifactStatus[]> {
  const { artifacts } = await requestJson<{ artifacts: ArtifactStatus[] }>('/api/artifacts/');
  return artifacts;
}

export function fetchSavedArtifact(kind: ArtifactKind): Promise<SavedArtifact> {
  return requestJson(`/api/artifacts/${kind}`);
}

/** `payload` is whatever working state that editor already POSTs to its /export route. */
export function saveArtifact(kind: ArtifactKind, payload: object): Promise<WorkspaceFile> {
  return requestJson(`/api/artifacts/${kind}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
}

export async function fetchWorkspaceFiles(): Promise<{ root: string; files: WorkspaceFile[] }> {
  return requestJson('/api/artifacts/files');
}

export function fetchWorkspaceFileContent(path: string): Promise<WorkspaceFileContent> {
  return requestJson(`/api/artifacts/files/content?path=${encodeURIComponent(path)}`);
}

/** "2.4 KB" / "918 B" -- for the file list. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "3 min ago", falling back to a plain date for anything older than a day. */
export function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'unknown';

  const when = new Date(iso);
  const secondsAgo = Math.max(0, (Date.now() - when.getTime()) / 1000);
  if (secondsAgo < 60) return 'just now';
  if (secondsAgo < 3600) return `${Math.floor(secondsAgo / 60)} min ago`;
  if (secondsAgo < 86400) return `${Math.floor(secondsAgo / 3600)} h ago`;
  return when.toLocaleDateString();
}

/** The "Saved 3 min ago" line the editors show next to their save button. */
export function formatSavedAt(iso: string | null): string {
  return iso ? `Saved ${formatRelativeTime(iso)}` : 'Not saved yet';
}
