// Top-level keys the semantic fields editor manages itself.
const EDITOR_KEYS = new Set(['Name', 'Fields', 'Building_ID_col', 'Num_Floors_col']);

/** Top-level keys the editor does not manage (e.g. globi's Height_col, WWR_col), kept so saving does not drop them. */
export function extraTopLevelKeys(doc: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(doc).filter(([key]) => !EDITOR_KEYS.has(key)));
}
