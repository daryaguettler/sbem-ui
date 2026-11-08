import type { ComponentPrior } from '../utils/componentPriors';

export interface FieldPreview {
  x: number[];
  density: number[];
  /** The n variant values, lowest first. */
  values: number[];
}

export interface PriorPreview {
  fields: Record<string, FieldPreview>;
  variants: Array<Record<string, number>>;
  errors: string[];
}

/** Each uncertain number's curve and values, and why any variant can't be built from the component. */
export async function previewPrior(componentType: string, name: string, prior: ComponentPrior): Promise<PriorPreview> {
  const response = await fetch('/api/component-priors/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ component_type: componentType, name, prior }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Preview failed (${response.status}).`);
  }
  return response.json();
}
