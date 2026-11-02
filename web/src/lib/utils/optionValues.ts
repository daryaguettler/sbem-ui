/**
 * The one value that tells options of a type apart (a lighting record by its W/m², a wall by
 * its U-value), so a choice can be shown by what it does rather than by its record name.
 */

type Rec = Record<string, unknown>;

const num = (value: unknown, digits = 2): string => {
  const n = Number(value);
  return Number.isFinite(n) ? String(Number(n.toFixed(digits))) : '?';
};

/** U-value of a construction's layers, 1/Σ(thickness/conductivity), as epinterface computes it. */
export function uValue(
  layers: Array<{ ConstructionMaterial?: unknown; Thickness?: unknown }>,
  conductivity: Record<string, number>
): number | null {
  let resistance = 0;
  for (const layer of layers) {
    const k = conductivity[String(layer.ConstructionMaterial ?? '')];
    const thickness = Number(layer.Thickness);
    if (!k || !Number.isFinite(thickness)) return null;
    resistance += thickness / k;
  }
  return resistance > 0 ? 1 / resistance : null;
}

/** "4.9 W/m²", "U 0.3 W/m²K", "NaturalGas · COP 0.9"; empty when the type has no headline value. */
export function keyValue(type: string, record: Rec | undefined, conductivity: Record<string, number> = {}): string {
  if (!record) return '';
  switch (type) {
    case 'Lighting':
    case 'Equipment':
      return `${num(record.PowerDensity)} W/m²`;
    case 'Occupancy':
      return `${num(record.PeopleDensity, 3)} people/m²`;
    case 'Thermostat':
      return `${num(record.HeatingSetpoint, 1)}–${num(record.CoolingSetpoint, 1)} °C`;
    case 'WaterUse':
      return `${num(record.FlowRatePerPerson, 4)} m³/day per person`;
    case 'ThermalSystem':
      return `${record.Fuel} · COP ${num(record.SystemCOP)}`;
    case 'DHW':
      return `${record.FuelType} · COP ${num(record.SystemCOP)}`;
    case 'Ventilation':
      return `${num(record.FreshAirPerPerson, 4)} m³/s per person${record.HRV && record.HRV !== 'NoHRV' ? ' · HRV' : ''}`;
    case 'Infiltration':
      return `${num(record.AirChangesPerHour)} ACH`;
    case 'GlazingConstructionSimple':
      return `U ${num(record.UValue)} · SHGC ${num(record.SHGF)}`;
    case 'ConstructionAssembly': {
      const u = uValue((record.Layers as Array<Rec>) ?? [], conductivity);
      return u === null ? `${((record.Layers as unknown[]) ?? []).length} layers` : `U ${num(u)} W/m²K`;
    }
    default:
      return '';
  }
}

/** The ConstructionAssembly Type a construction part's options have (FacadeAssembly -> Facade). */
export function constructionType(path: string): string {
  return (path.split('.').pop() as string).replace(/Assembly$/, '');
}
