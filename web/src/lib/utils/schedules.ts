// One schedule = day profiles (24 hourly values) + week patterns (weekday -> profile)
// + months (month -> week pattern). The server stores it as epinterface Day/Week/Year records.

export const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const;
export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;
export const CATEGORIES = ['Occupancy', 'Lighting', 'Equipment', 'WaterUse', 'Setpoint', 'Window'] as const;
export type Limit = 'Fraction' | 'Temperature' | 'AnyNumber';
export type Weekday = (typeof DAYS)[number];
export type Month = (typeof MONTHS)[number];

export interface ScheduleDraft {
  Name: string;
  Type: (typeof CATEGORIES)[number];
  Limit: Limit;
  profiles: Record<string, number[]>;
  weeks: Record<string, Record<Weekday, string>>;
  months: Record<Month, string>;
}

export const LIMITS: Record<Limit, { min: number; max: number; step: number }> = {
  Fraction: { min: 0, max: 1, step: 0.05 },
  Temperature: { min: -270, max: 1000, step: 0.5 },
  AnyNumber: { min: -1000, max: 1000, step: 0.1 },
};

export function clampToLimit(values: number[], limit: Limit): number[] {
  const { min, max } = LIMITS[limit];
  return values.map((v) => Math.min(max, Math.max(min, v)));
}

/** Snap to the limit's step, without float noise like 0.30000000000000004. */
export function snap(value: number, limit: Limit): number {
  const { step } = LIMITS[limit];
  return clampToLimit([Number((Math.round(value / step) * step).toFixed(4))], limit)[0];
}

export interface Parametric {
  /** Hour the peak starts (0-23) and ends (exclusive, 1-24); off < on wraps past midnight. */
  on: number;
  off: number;
  base: number;
  peak: number;
  /** Hours to ramp linearly from base to peak, and back, inside the on period. */
  ramp: number;
}

/** A base level with one peak period, e.g. occupied 8-18 at 1.0, else 0.1. */
export function parametric({ on, off, base, peak, ramp }: Parametric): number[] {
  const length = (off - on + 24) % 24 || 24;
  return Array.from({ length: 24 }, (_, h) => {
    const into = (h - on + 24) % 24; // hours since the peak started
    if (on === off) return peak;
    if (into >= length) return base;
    const edge = Math.min(into + 1, length - into); // 1 at the period's first/last hour
    const t = ramp > 0 ? Math.min(1, edge / (ramp + 1)) : 1;
    return Number((base + (peak - base) * t).toFixed(4));
  });
}

/** 24 numbers pasted from a spreadsheet column, a row, or typed with commas. */
export function parsePasted(text: string): number[] | string {
  const parts = text.trim().split(/[\s,;]+/).filter(Boolean);
  if (parts.length !== 24) return `Paste exactly 24 values, one per hour (got ${parts.length}).`;
  const values = parts.map(Number);
  const bad = parts.find((_, i) => !Number.isFinite(values[i]));
  return bad === undefined ? values : `"${bad}" is not a number.`;
}

const flat = (v: number) => Array<number>(24).fill(v);
const office = parametric({ on: 8, off: 18, base: 0.05, peak: 1, ramp: 1 });

/** Starting points per limit; the user edits from here. */
export const PRESETS: Record<string, { limit: Limit; values: number[] }> = {
  Office: { limit: 'Fraction', values: office },
  Residential: {
    limit: 'Fraction',
    values: [1, 1, 1, 1, 1, 1, 0.8, 0.6, 0.4, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.6, 0.8, 0.9, 0.9, 1, 1, 1],
  },
  Retail: { limit: 'Fraction', values: parametric({ on: 9, off: 21, base: 0.05, peak: 0.9, ramp: 1 }) },
  'Always on': { limit: 'Fraction', values: flat(1) },
  Off: { limit: 'Fraction', values: flat(0) },
  'Heating setpoint 21/16 °C': { limit: 'Temperature', values: parametric({ on: 6, off: 22, base: 16, peak: 21, ramp: 0 }) },
  'Cooling setpoint 24/28 °C': { limit: 'Temperature', values: parametric({ on: 6, off: 22, base: 28, peak: 24, ramp: 0 }) },
};

export function defaultDraft(name = '', type: ScheduleDraft['Type'] = 'Occupancy'): ScheduleDraft {
  const limit: Limit = type === 'Setpoint' ? 'Temperature' : 'Fraction';
  const weekday = limit === 'Temperature' ? PRESETS['Heating setpoint 21/16 °C'].values : office;
  return {
    Name: name,
    Type: type,
    Limit: limit,
    profiles: { Weekday: weekday, Weekend: limit === 'Temperature' ? weekday : flat(0.05) },
    weeks: { 'All year': Object.fromEntries(DAYS.map((d) => [d, d === 'Saturday' || d === 'Sunday' ? 'Weekend' : 'Weekday'])) as Record<Weekday, string> },
    months: Object.fromEntries(MONTHS.map((m) => [m, 'All year'])) as Record<Month, string>,
  };
}

/** Rename a profile or week pattern everywhere it's referenced; null if the name is taken or invalid. */
export function renameProfile(draft: ScheduleDraft, from: string, to: string): ScheduleDraft | null {
  to = to.trim();
  if (!to || to.includes('__') || (to !== from && to in draft.profiles)) return null;
  const profiles = Object.fromEntries(Object.entries(draft.profiles).map(([k, v]) => [k === from ? to : k, v]));
  const weeks = Object.fromEntries(
    Object.entries(draft.weeks).map(([w, p]) => [w, Object.fromEntries(DAYS.map((d) => [d, p[d] === from ? to : p[d]]))])
  ) as ScheduleDraft['weeks'];
  return { ...draft, profiles, weeks };
}

export function renameWeek(draft: ScheduleDraft, from: string, to: string): ScheduleDraft | null {
  to = to.trim();
  if (!to || to.includes('__') || (to !== from && to in draft.weeks)) return null;
  const weeks = Object.fromEntries(Object.entries(draft.weeks).map(([k, v]) => [k === from ? to : k, v]));
  const months = Object.fromEntries(MONTHS.map((m) => [m, draft.months[m] === from ? to : draft.months[m]])) as ScheduleDraft['months'];
  return { ...draft, weeks, months };
}

/** Drop a profile no week uses, or a week pattern no month uses; null if still in use. */
export function removeProfile(draft: ScheduleDraft, name: string): ScheduleDraft | null {
  if (Object.values(draft.weeks).some((p) => Object.values(p).includes(name))) return null;
  const { [name]: _, ...profiles } = draft.profiles;
  return { ...draft, profiles };
}

export function removeWeek(draft: ScheduleDraft, name: string): ScheduleDraft | null {
  if (Object.values(draft.months).includes(name)) return null;
  const { [name]: _, ...weeks } = draft.weeks;
  return { ...draft, weeks };
}

/** A name not yet in `taken`: "Profile", "Profile 2", ... */
export function freshName(base: string, taken: Record<string, unknown>): string {
  let name = base;
  for (let i = 2; name in taken; i++) name = `${base} ${i}`;
  return name;
}
