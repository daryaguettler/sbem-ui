import { writable } from 'svelte/store';
import type { ComponentMapState, ComponentMapViewMode } from '../types/componentMap';
import {
  addFieldToSelector,
  buildEmptyComponentMap,
  collapseChildrenAtPath,
  removeFieldFromSelector,
  removeSelectorAtPath,
  setSelectorAtPath,
} from '../utils/componentMapTree';

const initialState: ComponentMapState = {
  map: null,
  selectedTemplate: null,
  selectedPath: null,
  viewMode: 'graph',
  expandedPaths: [],
  valid: false,
  validationErrors: [],
  generatedNames: [],
};

const { subscribe, set, update } = writable<ComponentMapState>(initialState);

export const componentMapStore = {
  subscribe,
  set,
  update,
  loadFromTemplate: (templateData: Record<string, unknown>, templateName: string) => {
    update((state) => ({
      ...state,
      map: templateData,
      selectedTemplate: templateName,
      selectedPath: null,
      expandedPaths: [],
      valid: false,
      validationErrors: [],
      generatedNames: [],
    }));
  },
  startFromScratch: () => {
    update((state) => ({
      ...state,
      map: buildEmptyComponentMap(),
      selectedTemplate: null,
      selectedPath: 'Envelope',
      expandedPaths: [],
      valid: false,
      validationErrors: [],
      generatedNames: [],
    }));
  },
  setMap: (map: Record<string, unknown>) => {
    update((state) => ({
      ...state,
      map,
      valid: false,
      validationErrors: [],
      generatedNames: [],
    }));
  },
  setSelectedPath: (selectedPath: string | null) => {
    update((state) => ({ ...state, selectedPath }));
  },
  setViewMode: (viewMode: ComponentMapViewMode) => {
    update((state) => ({ ...state, viewMode }));
  },
  toggleExpandedPath: (path: string) => {
    update((state) => {
      const expanded = new Set(state.expandedPaths);
      if (expanded.has(path)) {
        expanded.delete(path);
      } else {
        expanded.add(path);
      }
      return { ...state, expandedPaths: [...expanded] };
    });
  },
  setSelector: (path: string, sourceFields: string[], suffix?: string) => {
    update((state) => {
      if (!state.map) return state;
      return {
        ...state,
        map: setSelectorAtPath(state.map, path, sourceFields, suffix),
        valid: false,
        validationErrors: [],
      };
    });
  },
  removeSelector: (path: string) => {
    update((state) => {
      if (!state.map) return state;
      return {
        ...state,
        map: removeSelectorAtPath(state.map, path),
        valid: false,
        validationErrors: [],
      };
    });
  },
  collapseChildren: (path: string) => {
    update((state) => {
      if (!state.map) return state;
      return {
        ...state,
        map: collapseChildrenAtPath(state.map, path),
        valid: false,
        validationErrors: [],
      };
    });
  },
  linkField: (path: string, fieldName: string) => {
    update((state) => {
      if (!state.map) return state;
      return {
        ...state,
        map: addFieldToSelector(state.map, path, fieldName),
        valid: false,
        validationErrors: [],
      };
    });
  },
  unlinkField: (path: string, fieldName: string) => {
    update((state) => {
      if (!state.map) return state;
      return {
        ...state,
        map: removeFieldFromSelector(state.map, path, fieldName),
        valid: false,
        validationErrors: [],
      };
    });
  },
  setValidation: (valid: boolean, errors: string[], generatedNames: string[] = []) => {
    update((state) => ({
      ...state,
      valid,
      validationErrors: errors,
      generatedNames,
    }));
  },
  reset: () => set(initialState),
};
