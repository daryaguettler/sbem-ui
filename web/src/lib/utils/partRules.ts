/**
 * Part rules (part-rules.yaml): what each model part depends on, and which library record
 * (option) each combination of those characteristics' values uses. Several rows can point at
 * one option, which is how Office and Hospital share a lighting record. The server compiles
 * the rules into the component map; these helpers are the edits the Component Map page makes.
 */

export interface PartRule {
  depends_on: string[];
  default: string | null;
  /** Row key (values in depends_on order, joined by SEP) -> option, only where it differs. */
  cells: Record<string, string>;
  /** "Same for every building" was answered; without it a part on its default is an assumption. */
  confirmed?: boolean;
}

export interface PartRules {
  assembly_base?: string | null;
  parts: Record<string, PartRule>;
}

export interface Row {
  key: string;
  values: Record<string, string>;
  option: string | null;
  /** The row has its own option rather than the default. */
  own: boolean;
}

export const SEP = '|';
export const GENERATED_PREFIX = 'auto_';
/** Marks the Scenario characteristic the server makes from retrofit packages. */

/** Fields the server writes into semantic-fields.yaml on every compile (Scenario, variant indices). */
export function isGeneratedField(field: { Description?: unknown }): boolean {
  return typeof field.Description === 'string' && field.Description.startsWith('Generated from ');
}

export function emptyRule(option: string | null = null): PartRule {
  return { depends_on: [], default: option, cells: {} };
}

function combinations(lists: string[][]): string[][] {
  return lists.reduce<string[][]>((acc, list) => acc.flatMap((combo) => list.map((value) => [...combo, value])), [[]]);
}

/** Every row of a rule, in value order, up to `limit`. */
export function rowsOf(rule: PartRule, options: Record<string, string[]>, limit = 500): Row[] {
  const lists = rule.depends_on.map((field) => options[field] ?? []);
  return combinations(lists)
    .slice(0, limit)
    .map((combo) => {
      const key = combo.join(SEP);
      const own = key in rule.cells;
      return {
        key,
        values: Object.fromEntries(rule.depends_on.map((field, i) => [field, combo[i]])),
        option: own ? rule.cells[key] : rule.default,
        own,
      };
    });
}

export function rowCount(rule: PartRule, options: Record<string, string[]>): number {
  return rule.depends_on.reduce((n, field) => n * (options[field]?.length ?? 0), 1);
}

/** Depend on one more characteristic: every row splits, and each new row keeps its option. */
export function withDependency(
  rule: PartRule,
  field: string,
  fieldOrder: string[],
  options: Record<string, string[]>
): PartRule {
  if (rule.depends_on.includes(field)) return rule;
  const rank = (name: string) => (fieldOrder.indexOf(name) === -1 ? Infinity : fieldOrder.indexOf(name));
  const depends_on = [...rule.depends_on, field].sort((a, b) => rank(a) - rank(b));
  const at = depends_on.indexOf(field);
  const cells: Record<string, string> = {};
  for (const [key, option] of Object.entries(rule.cells)) {
    const parts = key === '' ? [] : key.split(SEP);
    for (const value of options[field] ?? []) {
      cells[[...parts.slice(0, at), value, ...parts.slice(at)].join(SEP)] = option;
    }
  }
  return { ...rule, depends_on, cells, confirmed: false };
}

/**
 * Stop depending on a characteristic: rows that only differed by it merge. Where they had
 * different options, the most common one wins; `conflicts` counts those merged rows.
 */
export function withoutDependency(
  rule: PartRule,
  field: string,
  options: Record<string, string[]>
): { rule: PartRule; conflicts: number } {
  const at = rule.depends_on.indexOf(field);
  if (at === -1) return { rule, conflicts: 0 };
  const merged = new Map<string, string[]>();
  for (const row of rowsOf(rule, options, Infinity)) {
    const parts = row.key === '' ? [] : row.key.split(SEP);
    const key = [...parts.slice(0, at), ...parts.slice(at + 1)].join(SEP);
    merged.set(key, [...(merged.get(key) ?? []), row.option ?? '']);
  }
  const cells: Record<string, string> = {};
  let conflicts = 0;
  for (const [key, picks] of merged) {
    const counts = new Map<string, number>();
    picks.forEach((pick) => counts.set(pick, (counts.get(pick) ?? 0) + 1));
    if (counts.size > 1) conflicts += 1;
    // a tie keeps the default
    const winner = [...counts].sort((a, b) => b[1] - a[1] || Number(b[0] === rule.default) - Number(a[0] === rule.default))[0][0];
    if (winner && winner !== rule.default) cells[key] = winner;
  }
  return { rule: { ...rule, depends_on: rule.depends_on.filter((name) => name !== field), cells }, conflicts };
}

export function setOption(rule: PartRule, key: string, option: string): PartRule {
  const cells = { ...rule.cells };
  if (option === rule.default) delete cells[key];
  else cells[key] = option;
  return { ...rule, cells };
}

/** Change the option every row without its own uses. */
export function setDefault(rule: PartRule, option: string): PartRule {
  const cells = Object.fromEntries(Object.entries(rule.cells).filter(([, value]) => value !== option));
  return { ...rule, default: option, cells };
}

export type PartStatus = 'todo' | 'assumed' | 'same' | 'varies';

export function partStatus(rule: PartRule | undefined): PartStatus {
  if (!rule?.default) return 'todo';
  if (rule.depends_on.length > 0) return 'varies';
  return rule.confirmed ? 'same' : 'assumed';
}

/** One line per rule: "by Typology · Office, Hospital: LPD 10 · everything else: LPD 5". */
export function summary(rule: PartRule | undefined): string {
  if (!rule?.default) return 'No option yet';
  if (rule.depends_on.length === 0) return `Same for every building: ${rule.default}`;
  const byOption = new Map<string, string[]>();
  for (const [key, option] of Object.entries(rule.cells)) {
    byOption.set(option, [...(byOption.get(option) ?? []), key.split(SEP).join(' / ')]);
  }
  const groups = [...byOption].map(([option, keys]) =>
    `${keys.length > 3 ? `${keys.slice(0, 3).join(', ')} +${keys.length - 3}` : keys.join(', ')}: ${option}`
  );
  return [`by ${rule.depends_on.join(' × ')}`, ...groups, `${groups.length ? 'everything else' : 'every row'}: ${rule.default}`].join(' · ');
}

/** Every option a rule set uses, by part: a default no row falls back to is left out. */
export function optionsInUse(rules: PartRules, options: Record<string, string[]>): Record<string, string[]> {
  return Object.fromEntries(Object.entries(rules.parts).map(([path, rule]) => [path, usedOptions(rule, options)]));
}

/** Parts whose rules depend on a characteristic, for its card. */
export function partsUsing(rules: PartRules | null, field: string): string[] {
  if (!rules) return [];
  return Object.entries(rules.parts)
    .filter(([, rule]) => rule.depends_on.includes(field))
    .map(([path]) => path);
}

/** Rename a characteristic in every rule (row keys hold values, so they stay as they are). */
export function renameInRules(rules: PartRules, from: string, to: string): PartRules {
  return {
    ...rules,
    parts: Object.fromEntries(
      Object.entries(rules.parts).map(([path, rule]) => [
        path,
        { ...rule, depends_on: rule.depends_on.map((name) => (name === from ? to : name)) },
      ])
    ),
  };
}

/** Drop a removed characteristic from every rule, merging the rows it split. */
export function removeFromRules(rules: PartRules, field: string, options: Record<string, string[]>): PartRules {
  return {
    ...rules,
    parts: Object.fromEntries(
      Object.entries(rules.parts).map(([path, rule]) => [path, withoutDependency(rule, field, options).rule])
    ),
  };
}

/**
 * The options a rule actually uses, in the order its rows use them: one colour each on the
 * Component Map. The default counts only while some building still gets it.
 */
export function usedOptions(rule: PartRule, options: Record<string, string[]>, limit = 200): string[] {
  if (rule.depends_on.length === 0) return rule.default ? [rule.default] : [];
  const rows = rowsOf(rule, options, limit);
  const picks = rows.map((row) => row.option);
  if (rowCount(rule, options) > rows.length) picks.push(rule.default);
  return [...new Set(picks.filter((option): option is string => Boolean(option)))];
}
