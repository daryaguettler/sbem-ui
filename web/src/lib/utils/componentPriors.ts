/**
 * Component priors (component-priors.yaml): an optional curve on any number of a component,
 * which the server turns into n equally likely variants. This file holds the shapes the editor
 * offers, a starting curve around a component's current value, and the number each type is
 * best known by.
 */

export type Shape = 'uniform' | 'triangular' | 'normal' | 'lognormal' | 'beta' | 'histogram' | 'points' | 'empirical' | 'scipy';

export interface CurveSpec {
  shape: Shape;
  lower?: number | null;
  upper?: number | null;
  [param: string]: unknown;
}

/** independent, together, or a rank correlation between -1 and 1. */
export type Link = 'independent' | 'together' | number;

export interface ComponentPrior {
  n: number;
  fields: Record<string, CurveSpec>;
  link?: Link;
}

/** Parts whose variants move together (one shared index) or are correlated (drawn jointly). */
export interface PartLink {
  parts: string[];
  link: 'together' | number;
}

export interface ComponentPriorsDoc {
  components: Record<string, Record<string, ComponentPrior>>;
  links?: PartLink[];
}

/** A construction's U-value, which the server reaches by resizing the insulation. */
export const U = 'U';
export const DEFAULT_N = 5;

export type ParamKind = 'number' | 'list' | 'text' | 'pairs';
export interface ShapeInfo {
  id: Shape;
  label: string;
  params: Array<{ key: string; label: string; kind: ParamKind }>;
}

const num = (key: string, label: string) => ({ key, label, kind: 'number' as const });
const list = (key: string, label: string) => ({ key, label, kind: 'list' as const });

export const SHAPES: ShapeInfo[] = [
  { id: 'uniform', label: 'Even', params: [num('min', 'Min'), num('max', 'Max')] },
  { id: 'triangular', label: 'Triangle', params: [num('min', 'Min'), num('mode', 'Most likely'), num('max', 'Max')] },
  { id: 'normal', label: 'Bell (normal)', params: [num('mean', 'Mean'), num('std', 'Spread (std)')] },
  { id: 'lognormal', label: 'Skewed (lognormal)', params: [num('mean', 'Mean'), num('std', 'Spread (std)')] },
  { id: 'beta', label: 'Beta', params: [num('alpha', 'α'), num('beta', 'β'), num('min', 'Min'), num('max', 'Max')] },
  { id: 'histogram', label: 'Histogram', params: [list('edges', 'Bin edges'), list('weights', 'Weights')] },
  { id: 'points', label: 'Draw it', params: [list('x', 'Points (x)'), list('density', 'Heights')] },
  { id: 'empirical', label: 'From data', params: [list('values', 'Values')] },
  {
    id: 'scipy',
    label: 'Any scipy distribution',
    params: [
      { key: 'name', label: 'scipy.stats name', kind: 'text' },
      { key: 'params', label: 'Parameters', kind: 'pairs' },
    ],
  },
];

export function shapeInfo(shape: Shape): ShapeInfo {
  return SHAPES.find((info) => info.id === shape) ?? SHAPES[0];
}

const round = (value: number) => Number(value.toPrecision(3));

/** A curve of `shape` centred on a component's current `value` (±20%), to start editing from. */
export function defaultSpec(shape: Shape, value: number | null): CurveSpec {
  const v = value && Number.isFinite(value) && value !== 0 ? value : 1;
  const lo = round(Math.min(0.8 * v, 1.2 * v));
  const hi = round(Math.max(0.8 * v, 1.2 * v));
  const mid = round(v);
  const spread = round(Math.abs(0.1 * v));
  switch (shape) {
    case 'uniform':
      return { shape, min: lo, max: hi };
    case 'triangular':
      return { shape, min: lo, mode: mid, max: hi };
    case 'normal':
    case 'lognormal':
      return { shape, mean: mid, std: spread };
    case 'beta':
      return { shape, alpha: 2, beta: 2, min: lo, max: hi };
    case 'histogram':
      return { shape, edges: [lo, round(lo + (hi - lo) / 3), round(lo + (2 * (hi - lo)) / 3), hi], weights: [1, 2, 1] };
    case 'points':
      return { shape, x: [lo, mid, hi], density: [0, 1, 0] };
    case 'empirical':
      return { shape, values: [mid] };
    case 'scipy':
      return { shape, name: 'gamma', params: { a: 4, scale: round(Math.abs(v) / 4) } };
  }
}

/** Layers at or below this conductivity (W/mK) are insulation, as the server counts them. */
export const INSULATING = 0.06;

/** Whether a construction has an insulation layer the server can thin as well as thicken. */
export function insulated(layers: Array<Record<string, unknown>>, conductivity: Record<string, number>): boolean {
  return layers.some((layer) => (conductivity[String(layer.ConstructionMaterial ?? '')] ?? Infinity) <= INSULATING);
}

/** A U-value curve for a construction without insulation: it can only get better than it is. */
export function uninsulatedSpec(u: number): CurveSpec {
  const max = Math.floor(u * 1000) / 1000; // rounding up would ask for a U it can't reach
  return { shape: 'triangular', min: round(0.6 * u), mode: round(0.85 * u), max };
}

/** "0.6, 0.9 1.1" -> [0.6, 0.9, 1.1]; anything that isn't a number is dropped. */
export function parseList(text: string): number[] {
  return text
    .split(/[\s,;]+/)
    .filter(Boolean)
    .map(Number)
    .filter((n) => Number.isFinite(n));
}

/** "a=2, scale=0.5" -> {a: 2, scale: 0.5}. */
export function parsePairs(text: string): Record<string, number> {
  return Object.fromEntries(
    text
      .split(/[,;]+/)
      .map((pair) => pair.split('=').map((part) => part.trim()))
      .filter(([key, value]) => key && value && Number.isFinite(Number(value)))
      .map(([key, value]) => [key, Number(value)])
  );
}

export function formatPairs(pairs: unknown): string {
  return Object.entries((pairs as Record<string, unknown>) ?? {})
    .map(([key, value]) => `${key}=${value}`)
    .join(', ');
}

/** The number a type is best known by, offered first when making a component uncertain. */
export function keyField(type: string): string | null {
  const fields: Record<string, string> = {
    ConstructionAssembly: U,
    GlazingConstructionSimple: 'UValue',
    Infiltration: 'AirChangesPerHour',
    Lighting: 'PowerDensity',
    Equipment: 'PowerDensity',
    Occupancy: 'PeopleDensity',
    Thermostat: 'HeatingSetpoint',
    WaterUse: 'FlowRatePerPerson',
    ThermalSystem: 'SystemCOP',
    DHW: 'SystemCOP',
    Ventilation: 'FreshAirPerPerson',
  };
  return fields[type] ?? null;
}

/** `doc`'s links with one link replaced (null removes it); links of fewer than 2 parts are dropped. */
export function withLink(doc: ComponentPriorsDoc, index: number, link: PartLink | null): ComponentPriorsDoc {
  const links = [...(doc.links ?? [])];
  if (index >= links.length) links.push(link as PartLink);
  else if (link) links[index] = link;
  else links.splice(index, 1);
  return { ...doc, links: links.filter((l) => l && l.parts.length > 0) };
}

/** The prior on a component, if it has one. */
export function priorFor(doc: ComponentPriorsDoc, type: string, name: string | null): ComponentPrior | null {
  return name ? (doc.components[type]?.[name] ?? null) : null;
}

/** `doc` with component `name`'s prior replaced (null removes it, and an emptied type). */
export function withPrior(doc: ComponentPriorsDoc, type: string, name: string, prior: ComponentPrior | null): ComponentPriorsDoc {
  const ofType = { ...(doc.components[type] ?? {}) };
  if (prior && Object.keys(prior.fields).length > 0) ofType[name] = prior;
  else delete ofType[name];
  const components = { ...doc.components, [type]: ofType };
  if (Object.keys(ofType).length === 0) delete components[type];
  return { ...doc, components };
}
