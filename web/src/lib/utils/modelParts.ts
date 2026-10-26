/**
 * Plain-language names for the parts of the energy model a characteristic can change.
 *
 * Each part is one or more component-tree paths (the GloBI component map keys).
 * Parts are mostly one path each because sibling components are usually chosen by
 * different characteristics (e.g. ground slab vs basement walls). Tree paths not
 * listed here (schedules, parent groups) show up as "More parts" under their path.
 */

export type ModelPartGroup = 'Envelope' | 'Systems' | 'Use';

export interface ModelPart {
  id: string;
  label: string;
  group: ModelPartGroup;
  paths: string[];
}

const ASSEMBLIES = 'Envelope.Assemblies';
const SPACE_USE = 'Operations.SpaceUse';
const CONDITIONING = 'Operations.HVAC.ConditioningSystems';

export const MODEL_PARTS: ModelPart[] = [
  { id: 'walls', label: 'Walls', group: 'Envelope', paths: [`${ASSEMBLIES}.FacadeAssembly`] },
  { id: 'windows', label: 'Windows', group: 'Envelope', paths: ['Envelope.Window'] },
  {
    id: 'roof',
    label: 'Roof',
    group: 'Envelope',
    paths: [`${ASSEMBLIES}.FlatRoofAssembly`, `${ASSEMBLIES}.AtticRoofAssembly`],
  },
  { id: 'attic-floor', label: 'Attic floor', group: 'Envelope', paths: [`${ASSEMBLIES}.AtticFloorAssembly`] },
  { id: 'ground-slab', label: 'Ground slab', group: 'Envelope', paths: [`${ASSEMBLIES}.GroundSlabAssembly`] },
  { id: 'basement-walls', label: 'Basement walls', group: 'Envelope', paths: [`${ASSEMBLIES}.GroundWallAssembly`] },
  {
    id: 'basement-ceiling',
    label: 'Basement ceiling',
    group: 'Envelope',
    paths: [`${ASSEMBLIES}.BasementCeilingAssembly`],
  },
  { id: 'exposed-floor', label: 'Exposed floor', group: 'Envelope', paths: [`${ASSEMBLIES}.ExternalFloorAssembly`] },
  {
    id: 'interior',
    label: 'Interior partitions and floors',
    group: 'Envelope',
    paths: [
      `${ASSEMBLIES}.PartitionAssembly`,
      `${ASSEMBLIES}.FloorCeilingAssembly`,
      `${ASSEMBLIES}.InternalMassAssembly`,
    ],
  },
  { id: 'air-leakage', label: 'Air leakage', group: 'Envelope', paths: ['Envelope.Infiltration'] },
  { id: 'attic-air-leakage', label: 'Attic air leakage', group: 'Envelope', paths: ['Envelope.AtticInfiltration'] },
  {
    id: 'basement-air-leakage',
    label: 'Basement air leakage',
    group: 'Envelope',
    paths: ['Envelope.BasementInfiltration'],
  },
  { id: 'heating', label: 'Heating', group: 'Systems', paths: [`${CONDITIONING}.Heating`] },
  { id: 'cooling', label: 'Cooling', group: 'Systems', paths: [`${CONDITIONING}.Cooling`] },
  { id: 'ventilation', label: 'Ventilation', group: 'Systems', paths: ['Operations.HVAC.Ventilation'] },
  { id: 'hot-water', label: 'Hot water system', group: 'Systems', paths: ['Operations.DHW'] },
  { id: 'occupancy', label: 'Occupancy', group: 'Use', paths: [`${SPACE_USE}.Occupancy`] },
  { id: 'lighting', label: 'Lighting', group: 'Use', paths: [`${SPACE_USE}.Lighting`] },
  { id: 'equipment', label: 'Equipment (plug loads)', group: 'Use', paths: [`${SPACE_USE}.Equipment`] },
  { id: 'thermostat', label: 'Thermostat setpoints', group: 'Use', paths: [`${SPACE_USE}.Thermostat`] },
  { id: 'water-use', label: 'Hot water use', group: 'Use', paths: [`${SPACE_USE}.WaterUse`] },
];

/** Tree paths no named part covers, in tree order. */
export function otherPaths(treePaths: string[]): string[] {
  const covered = new Set(MODEL_PARTS.flatMap((part) => part.paths));
  return treePaths.filter((path) => !covered.has(path));
}

/**
 * A record-name suffix for a new selector at `path`, so components that share a
 * library table (all assemblies are ConstructionAssembly, heating and cooling are both
 * ThermalSystem) don't resolve to the same record. None when the type is unique.
 */
export function defaultSuffix(
  path: string,
  nodesByPath: Record<string, { componentType: string | null }>
): string | undefined {
  const type = nodesByPath[path]?.componentType;
  if (!type) return undefined;
  const sharing = Object.keys(nodesByPath).filter((other) => other !== path && nodesByPath[other]?.componentType === type);
  if (sharing.length === 0) return undefined;
  const short = (p: string) => (p.split('.').pop() as string).replace(/Assembly$/, '');
  const name = short(path);
  if (!sharing.some((other) => short(other) === name)) return name;
  // e.g. the Schedule under Lighting vs the one under Equipment
  const segments = path.split('.');
  return `${segments[segments.length - 2]}${name}`;
}
