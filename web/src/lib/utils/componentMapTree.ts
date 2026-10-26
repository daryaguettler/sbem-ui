import { get } from 'svelte/store';
import type { ComponentSelector, ComponentSelectorRecord } from '../types/componentMap';
import { componentTreeStore, type ComponentTreeNode } from '../stores/componentTreeStore';
import { SERIES_HEX } from './priorViz';

export type ComponentLevel = {
  id: string;
  name: string;
  displayName: string;
  path: string;
  depth: number;
  description: string;
};

/**
 * A semantic field's color on the component graph: the validated categorical
 * palette, by the field's position, in fixed order. Returned as hex (not a CSS
 * variable) because xyflow bakes edge marker colors into SVG ids, so the caller
 * passes the resolved theme. Fields past the eighth share a neutral gray rather
 * than recycling a hue -- the edge still ends at a labeled field node.
 */
export function fieldColor(index: number, theme: 'light' | 'dark' = 'light'): string {
  const slots = SERIES_HEX[theme];
  return index >= 0 && index < slots.length ? slots[index] : theme === 'dark' ? '#6f7682' : '#9ca3af';
}

function toComponentId(path: string): string {
  return `component_${path.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`;
}

function walkComponents(
  nodesByPath: Record<string, ComponentTreeNode>,
  path: string,
  depth: number,
  levels: ComponentLevel[]
): void {
  const info = nodesByPath[path];
  if (!info) return;

  levels.push({
    id: toComponentId(path),
    name: info.displayName,
    displayName: info.displayName,
    path,
    depth,
    description: info.componentType ?? '',
  });

  for (const childPath of info.children) {
    walkComponents(nodesByPath, childPath, depth + 1, levels);
  }
}

/** Reads the live component tree (fetched from GET /api/component-tree/ at app
 * boot, sourced from epinterface's real ZoneComponent graph -- see
 * componentTreeStore.ts) rather than a hardcoded schema. */
export function buildComponentLevels(): ComponentLevel[] {
  const tree = get(componentTreeStore);
  const levels: ComponentLevel[] = [];
  for (const root of tree.roots) {
    walkComponents(tree.nodesByPath, root, 0, levels);
  }
  return levels;
}

function buildNode(nodesByPath: Record<string, ComponentTreeNode>, path: string): Record<string, unknown> {
  const info = nodesByPath[path];
  if (!info || info.children.length === 0) {
    return {};
  }

  const node: Record<string, unknown> = {};
  for (const childPath of info.children) {
    const key = childPath.split('.').pop() as string;
    node[key] = buildNode(nodesByPath, childPath);
  }
  return node;
}

export function buildEmptyComponentMap(): Record<string, unknown> {
  const tree = get(componentTreeStore);
  const map: Record<string, unknown> = {};
  for (const root of tree.roots) {
    map[root] = buildNode(tree.nodesByPath, root);
  }
  return map;
}

function deepCopy<T>(value: T): T {
  return structuredClone(value);
}

export function getNodeAtPath(
  componentMap: Record<string, unknown>,
  path: string
): Record<string, unknown> | null {
  if (!path) return componentMap;

  let node: unknown = componentMap;
  for (const part of path.split('.')) {
    if (!node || typeof node !== 'object' || !(part in (node as Record<string, unknown>))) {
      return null;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return node && typeof node === 'object' ? (node as Record<string, unknown>) : null;
}

export function getSelectorAtPath(
  componentMap: Record<string, unknown>,
  path: string
): ComponentSelector | null {
  const node = getNodeAtPath(componentMap, path);
  if (!node?.selector || typeof node.selector !== 'object') {
    return null;
  }
  const selector = node.selector as Record<string, unknown>;
  return {
    source_fields: (selector.source_fields as string[]) || [],
    suffix: selector.suffix as string | undefined,
  };
}

export function collectSelectors(
  node: Record<string, unknown>,
  path = ''
): ComponentSelectorRecord[] {
  const results: ComponentSelectorRecord[] = [];

  if (node.selector && typeof node.selector === 'object') {
    const selector = node.selector as Record<string, unknown>;
    results.push({
      path: path || 'root',
      source_fields: (selector.source_fields as string[]) || [],
      suffix: selector.suffix as string | undefined,
    });
  }

  for (const [key, value] of Object.entries(node)) {
    if (key === 'selector' || !value || typeof value !== 'object') continue;
    const childPath = path ? `${path}.${key}` : key;
    results.push(...collectSelectors(value as Record<string, unknown>, childPath));
  }

  return results;
}

export function setSelectorAtPath(
  componentMap: Record<string, unknown>,
  path: string,
  sourceFields: string[],
  suffix?: string
): Record<string, unknown> {
  const updated = deepCopy(componentMap);
  const node = getNodeAtPath(updated, path);
  if (!node) {
    throw new Error(`component path '${path}' not found`);
  }

  const selector: Record<string, unknown> = { source_fields: sourceFields };
  if (suffix) {
    selector.suffix = suffix;
  }
  node.selector = selector;
  return updated;
}

export function removeSelectorAtPath(
  componentMap: Record<string, unknown>,
  path: string
): Record<string, unknown> {
  const updated = deepCopy(componentMap);
  const node = getNodeAtPath(updated, path);
  if (!node) return updated;
  delete node.selector;
  return updated;
}

function stripSelectors(node: Record<string, unknown>): void {
  delete node.selector;
  for (const value of Object.values(node)) {
    if (value && typeof value === 'object') {
      stripSelectors(value as Record<string, unknown>);
    }
  }
}

export function collapseChildrenAtPath(
  componentMap: Record<string, unknown>,
  path: string
): Record<string, unknown> {
  const updated = deepCopy(componentMap);
  const node = getNodeAtPath(updated, path);
  if (!node) return updated;

  for (const [key, value] of Object.entries(node)) {
    if (key === 'selector' || !value || typeof value !== 'object') continue;
    stripSelectors(value as Record<string, unknown>);
  }
  return updated;
}

export function getParentPath(path: string): string | null {
  const parts = path.split('.');
  if (parts.length <= 1) return null;
  return parts.slice(0, -1).join('.');
}

export function hasSelectorOnPathOrAncestor(
  componentMap: Record<string, unknown>,
  path: string
): boolean {
  const parts = path.split('.');
  for (let i = 1; i <= parts.length; i += 1) {
    const ancestorPath = parts.slice(0, i).join('.');
    if (getSelectorAtPath(componentMap, ancestorPath)) {
      return true;
    }
  }
  return false;
}

export function getEffectiveSelector(
  componentMap: Record<string, unknown>,
  path: string
): { path: string; selector: ComponentSelector } | null {
  const parts = path.split('.');
  for (let i = parts.length; i >= 1; i -= 1) {
    const currentPath = parts.slice(0, i).join('.');
    const selector = getSelectorAtPath(componentMap, currentPath);
    if (selector) {
      return { path: currentPath, selector };
    }
  }
  return null;
}

export type SelectorStatus = 'unmapped' | 'mapped' | 'inherited';

export function getSelectorStatus(
  componentMap: Record<string, unknown>,
  path: string
): SelectorStatus {
  if (getSelectorAtPath(componentMap, path)) {
    return 'mapped';
  }
  const parentPath = getParentPath(path);
  if (parentPath && getSelectorAtPath(componentMap, parentPath)) {
    return 'inherited';
  }
  return 'unmapped';
}

export function previewSelectorNames(
  sourceFields: string[],
  semanticFields: Array<{ name: string; options?: string[] }>,
  suffix?: string,
  limit = 20
): { count: number; samples: string[] } {
  const fieldOptions = Object.fromEntries(
    semanticFields.filter((field) => field.name).map((field) => [field.name, field.options || []])
  );

  if (sourceFields.length === 0) {
    return { count: 0, samples: [] };
  }

  const optionLists = sourceFields.map((name) => fieldOptions[name] || [name]);
  const names: string[] = [];

  const build = (index: number, parts: string[]) => {
    if (index >= optionLists.length) {
      const combo = [...parts];
      if (suffix) combo.push(suffix);
      names.push(combo.join('_'));
      return;
    }
    for (const option of optionLists[index]) {
      build(index + 1, [...parts, option]);
    }
  };

  build(0, []);
  const unique = [...new Set(names)].sort();
  return { count: unique.length, samples: unique.slice(0, limit) };
}

export type SelectorCombination = { name: string; values: Record<string, string> };

/** Like previewSelectorNames, but keeps each combination's per-field values
 * (e.g. {Age_bracket: "pre_1975", Size_bucket: "small"}) alongside the
 * generated name -- the coverage grid needs both: the name to check/create a
 * component record for, and the field values to show as columns. */
export function buildSelectorCombinations(
  sourceFields: string[],
  semanticFields: Array<{ name: string; options?: string[] }>,
  suffix?: string
): SelectorCombination[] {
  const fieldOptions = Object.fromEntries(
    semanticFields.filter((field) => field.name).map((field) => [field.name, field.options || []])
  );

  if (sourceFields.length === 0) return [];

  const optionLists = sourceFields.map((name) => fieldOptions[name] || [name]);
  const combinations: SelectorCombination[] = [];

  const build = (index: number, values: Record<string, string>, parts: string[]) => {
    if (index >= sourceFields.length) {
      const nameParts = suffix ? [...parts, suffix] : parts;
      combinations.push({ name: nameParts.join('_'), values: { ...values } });
      return;
    }
    const fieldName = sourceFields[index];
    for (const option of optionLists[index]) {
      build(index + 1, { ...values, [fieldName]: option }, [...parts, option]);
    }
  };

  build(0, {}, []);
  return combinations;
}

export function addFieldToSelector(
  componentMap: Record<string, unknown>,
  path: string,
  fieldName: string
): Record<string, unknown> {
  const existing = getSelectorAtPath(componentMap, path);
  const sourceFields = existing?.source_fields || [];
  if (sourceFields.includes(fieldName)) {
    return componentMap;
  }
  return setSelectorAtPath(componentMap, path, [...sourceFields, fieldName], existing?.suffix);
}

export function removeFieldFromSelector(
  componentMap: Record<string, unknown>,
  path: string,
  fieldName: string
): Record<string, unknown> {
  const existing = getSelectorAtPath(componentMap, path);
  if (!existing) return componentMap;

  const nextFields = existing.source_fields.filter((name) => name !== fieldName);
  if (nextFields.length === 0) {
    return removeSelectorAtPath(componentMap, path);
  }
  return setSelectorAtPath(componentMap, path, nextFields, existing.suffix);
}

/** How a field reaches a component: its own selector, an ancestor's, or not at all.
 * A child's own selector replaces its parent's, so an ancestor only counts when the
 * path has no selector of its own. */
export function fieldStatusAtPath(
  componentMap: Record<string, unknown>,
  path: string,
  fieldName: string
): { status: 'own' | 'inherited' | 'off'; from?: string } {
  const effective = getEffectiveSelector(componentMap, path);
  if (!effective?.selector.source_fields.includes(fieldName)) return { status: 'off' };
  return effective.path === path ? { status: 'own' } : { status: 'inherited', from: effective.path };
}

/** Insert `fieldName` without reordering the existing fields (that would rename every
 * record): it goes before the first existing field that `fieldOrder` puts after it. */
function insertInOrder(sourceFields: string[], fieldName: string, fieldOrder: string[]): string[] {
  const rank = (name: string) => {
    const index = fieldOrder.indexOf(name);
    return index === -1 ? Infinity : index;
  };
  const at = sourceFields.findIndex((name) => rank(name) > rank(fieldName));
  return at === -1 ? [...sourceFields, fieldName] : [...sourceFields.slice(0, at), fieldName, ...sourceFields.slice(at)];
}

/**
 * Make `fieldName` choose (or stop choosing) the component at `path`.
 *
 * Turning it on where the path only inherits a parent's selector creates a child
 * override from the parent's fields plus this one, so sibling components keep the
 * records they have. Turning it off only touches the path's own selector.
 */
export function setPartForField(
  componentMap: Record<string, unknown>,
  path: string,
  fieldName: string,
  on: boolean,
  fieldOrder: string[],
  /** Suffix for a selector this creates (see modelParts.defaultSuffix); an existing one keeps its own. */
  suffixForNew?: string
): Record<string, unknown> {
  if (!on) return removeFieldFromSelector(componentMap, path, fieldName);

  const effective = getEffectiveSelector(componentMap, path);
  if (effective?.selector.source_fields.includes(fieldName)) return componentMap;
  const own = effective?.path === path ? effective.selector : null;
  const base = effective?.selector.source_fields ?? [];
  const suffix = own ? own.suffix : suffixForNew;
  return setSelectorAtPath(componentMap, path, insertInOrder(base, fieldName, fieldOrder), suffix);
}

/** Rename a field in every selector, keeping each selector's field order. */
export function renameFieldInMap(
  componentMap: Record<string, unknown>,
  from: string,
  to: string
): Record<string, unknown> {
  let updated = componentMap;
  for (const record of collectSelectors(componentMap)) {
    if (!record.source_fields.includes(from)) continue;
    const fields = record.source_fields.map((name) => (name === from ? to : name));
    updated = setSelectorAtPath(updated, record.path, fields, record.suffix);
  }
  return updated;
}

export function isComponentVisible(
  componentMap: Record<string, unknown>,
  path: string,
  expandedPaths: Set<string>
): boolean {
  const parentPath = getParentPath(path);
  if (!parentPath) return true;

  const parentSelector = getSelectorAtPath(componentMap, parentPath);
  if (parentSelector && !expandedPaths.has(parentPath)) {
    return false;
  }

  return isComponentVisible(componentMap, parentPath, expandedPaths);
}

export function countHiddenChildren(
  componentMap: Record<string, unknown>,
  path: string,
  levels: ComponentLevel[],
  expandedPaths: Set<string>
): number {
  return levels.filter(
    (level) =>
      level.path.startsWith(`${path}.`) &&
      !isComponentVisible(componentMap, level.path, expandedPaths)
  ).length;
}
