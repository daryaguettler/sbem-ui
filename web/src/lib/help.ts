/**
 * How-to text for Explain mode, one entry per page section. In Minimal mode the same
 * text sits behind a "?" next to the section heading (components/Explain.svelte).
 * Write it as design guidance: what a good choice looks like, not what the control is.
 */
export const HELP = {
  gis: {
    page: "Upload your building data, match its columns to the model's inputs, and check for missing values.",
    upload:
      'CSV or GeoJSON, one row per building. Include an ID, floor count, and every attribute you will classify or stratify by later (year built, use, floor area): columns left out here cannot drive rules or strata in later steps.',
    match:
      "Pick which of your columns holds each model input. Required inputs must be matched; recommended ones improve results when your data has them.",
    missing:
      'Tick the columns later steps depend on. A building missing a value there cannot be classified, so it is better caught here. Leave optional columns unticked so their gaps do not drop buildings.',
    validate:
      'Validating saves the cleaned dataset that every later step reads. If you drop incomplete rows, check the remaining count is still representative of the stock.',
  },
  characteristics: {
    page: 'The few things about each building that change its energy use, such as age, typology or heating system. For each one, say what values it can take, how we know it for every building, and which parts of the energy model it changes.',
    globi: 'GloBI calls these semantic fields; they are saved to semantic-fields.yaml.',
    list: 'Characteristics from your data come first, then estimated ones in the order they are drawn: each estimate comes after the characteristics it depends on. Every characteristic multiplies the library records and estimate rows you need, so keep the list short.',
    values:
      'Keep values few (2–6) and mutually exclusive, so every building has exactly one. Short, code-like names (pre_1975, SFH) work best: they become parts of library record names.',
    howKnown:
      '“From my data”: a rule on one of your GIS columns decides the value for every building, e.g. age band from year built. “Estimate it”: your data does not record it, e.g. heating system, so each simulated building draws a value from probabilities you set. The same building can come out differently in different draws; that spread is how the model carries what you do not know.',
    estimate:
      'The odds of each value, optionally different for different kinds of building (depends on). GloBI calls this a prior; it is saved to priors/priors.yaml.',
    parts:
      'Which parts of the energy model differ by this characteristic. Each part picks a library record by joining the values of the characteristics that choose it, so every one you add multiplies the records needed. GloBI calls this the component map.',
    connections:
      'Every model part and the characteristics that choose it. A part with none of its own uses its parent group’s choice. Edit here when one choice should cover a whole group, e.g. all assemblies by region.',
    files:
      'What this page saves, exactly as GloBI reads it: semantic-fields.yaml (characteristics), component-map.yaml (model parts) and priors/priors.yaml (estimates). Point a GloBI run at these files.',
    inspect:
      'Follow one real building through the model as it stands now, saved or not: its values from data, its estimated values over many draws, and the library record each model part picks.',
    check:
      'Checks all three files the way GloBI will read them: every characteristic complete, every model part pointing at defined characteristics, every estimate covering its values. Run it before a simulation.',
    budget:
      'Library records: one per combination of values, for every model part. Estimate rows: one per combination an estimate depends on. Both grow multiplicatively with each characteristic you add.',
    save: 'Saves every file with unsaved changes: semantic-fields.yaml, component-map.yaml and priors/priors.yaml.',
  },
  /** Help for the pieces of the characteristics page that grew out of the old per-file editors. */
  semanticFields: {
    ranges:
      "Each value covers a range of the column, e.g. 0–1974 → pre_1975. Cover the column's whole span with no gaps, so no building falls between bands.",
    mapping:
      'Pick which value each entry in the column becomes. Group entries by how they behave energetically, not by how they are labelled, and map every entry that occurs: unmapped entries leave buildings without a value.',
  },
  componentLibrary: {
    page: 'The engineering records (lighting power, infiltration, HVAC efficiency, schedules…) that model parts point to.',
    records:
      "A model part picks a record by joining its characteristics' values with “_” (e.g. SFH_pre_1975), so name records that way. Each characteristic's card on Building Characteristics lists the records its parts need and which are missing.",
  },
  priorTrees: {
    generate:
      'Pick what genuinely changes the odds, e.g. heating system by age band. Each one you add multiplies the table rows, so prefer one or two and watch the row count and coverage before adding more. Estimate from data when a column records this for part of the stock; otherwise start from an even split and edit towards published statistics.',
    order:
      'Estimates are drawn left to right, and one can only depend on those drawn before it, so there can be no loops.',
    preview: 'Draw from the estimates over your own buildings to see what they produce before saving.',
  },
  retrofits: {
    page: 'Bundle upgrades into packages, e.g. “oil boiler → heat pump where built before 1975”.',
    packages:
      "Make one package per option you want to compare (e.g. “envelope only” vs “envelope + heat pump”); each is compared against the baseline. Add an “if” condition so a measure only hits buildings where it makes sense.",
    order:
      'Tick a field and order its options from worst (left) to best (right); measures then only move a building rightwards.',
  },
  sampling: {
    page: 'How many buildings to simulate for training, and how to split the stock for prediction.',
    training:
      'Stratify by the columns that most change energy use, and give small strata enough simulations to converge. Start small and raise the numbers once a run completes.',
    prediction: 'Split by a column that gives jobs of a manageable size, such as municipality.',
  },
  modelExecution: {
    page: 'Check readiness and export a snapshot.',
    pageRunner: 'Check readiness, validate inputs and run a small local test.',
    readiness: 'Every step must be complete before a run. “Go to step” opens whatever is missing.',
    inputs: "Checks this project's inputs against what the runner expects, before you spend time on a run.",
    testRun:
      'Simulates a handful of buildings locally to catch errors and sanity-check EUI and savings before a full run.',
    export:
      "A JSON snapshot of this project's editors, for sharing or archiving. It is not a globi manifest.yml and can't be passed to globi submit.",
  },
  projectFiles: {
    page: 'Everything saved in this project on disk. Open a file to read it, or load a saved artifact straight back into its editor.',
  },
};
