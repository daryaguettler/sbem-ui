# SBEM UI

A browser UI for building SBEM (Simplified Building Energy Model) inputs without writing
YAML by hand. You upload GIS data for a building stock, describe the characteristics that
drive energy use, set probabilities for the ones your data doesn't record, define retrofit
packages, and the app writes the files that GloBI reads.

## Architecture

- **Frontend**: Svelte 5, TypeScript and Vite (`web/`). Graph views use `@xyflow/svelte`.
- **Backend**: FastAPI (`server/`).
- **Libraries**: `epinterface` provides the component graph and the Prisma-backed SQLite
  component library used by `globi`. `semantic_priors` (prior-tree schema and sampling
  engine) is vendored in `lib/semantic_priors` (see its `VENDORED.md`).
- **Persistence**: a project workspace is a directory on disk. It holds the semantic
  fields, component map, priors, GIS files and a real `components-lib.db`. The backend
  reads and writes it directly, so there is no separate database server. The browser
  remembers the last project you opened.

## Setup

### Prerequisites

- Node.js 18+
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A [globi](https://github.com/MITSustainableDesignLab/globi) checkout next to this repo
  (`../globi`). sbem-ui depends on it, and globi sets the `epinterface` version, so the
  component library you edit here is the one globi simulates.
- Network access for the first setup (Prisma downloads its query-engine binaries)
- Docker, only for **Single Building** runs (globi's `make cli simulate-flat`)

### Install

```bash
make setup
```

This runs three steps, which you can also run yourself:

```bash
uv sync                          # Python deps, including globi, epinterface and prisma
uv run epinterface prisma generate   # one-time: generate the Prisma client
cd web && npm install            # frontend deps
```

`prisma generate` downloads platform-specific binaries from Prisma's CDN. It fails with
an unclear error if the network is restricted.

### Run

```bash
make dev
```

This starts the backend on `http://localhost:8000` and the frontend on
`http://localhost:5173`. Ctrl+C stops both. To run them separately, use `make backend`
and `make frontend`.

Interactive API docs are at `http://localhost:8000/docs`.

### Optional: AI drafting

The Building Characteristics page can draft a characteristic for you with Claude. Set
`ANTHROPIC_API_KEY` in the backend's environment before starting it to enable this. The
rest of the app works without it.

### Tests and checks

```bash
make test       # Python tests (pytest)
make test-web   # frontend logic tests (Node's built-in test runner)
make check      # svelte-check type checking
```

## Using the app

### 1. Open a project

On first load the app asks you to create or open a project workspace. Creating one makes
the directory and provisions its `components-lib.db`, which takes a few seconds. Pick a
**Component library** template instead of an empty one: **GloBI starter library** (globi's
materials and schedules, to build the rest yourself) or **GloBI tutorial library** (globi's
complete e2e library). Both include Boston weather. Use **Switch project** at the bottom
of the sidebar to change projects later.

Create projects inside your globi checkout (e.g. `globi/inputs/my-model`, which globi
gitignores) if you want to run them: Single Building requires it, and the generated run
files then use repo-relative paths that globi's Docker runs can see.

A project looks like this on disk:

```
<project>/
├── project.json                  # name, created date, schema version
├── gis/                          # uploaded GIS file, cleaned data, column mappings
├── semantic-fields.yaml          # building characteristics
├── component-map.selectors.yaml  # which characteristics choose each model part
├── component-map.yaml            # generated component map
├── components-lib.db             # component library (epinterface schema)
├── priors/priors.yaml            # estimates for characteristics not in your data
├── schedule-variability.yaml     # per-building schedule noise (globi config)
├── retrofits.yaml                # retrofit packages
├── sampling.yaml                 # sampling settings
├── gis/buildings-sampled.geojson # buildings x prior draws, written by Sampling
├── building.yml, manifest.yml,   # globi run files, generated in Model Execution
│   artifacts.yml, gis-preprocessor.yml
├── flat-building.yml             # Single Building parameters
└── weather/                      # weather .zip files (a template project ships one)
```

`project.json` can remap any of these paths with a `"files"` map, so an existing repo
layout (such as a globi `inputs/` folder) can be opened as a project.

### 2. Work through the steps

The sidebar lists the steps in order. A step shows a check once its readiness checks pass;
hover over it to see what is missing.

1. **GIS Cleaning**. Upload a CSV or GeoJSON with one row per building, or use the sample
   buildings (globi's 100-building tutorial stock). Match your
   columns to the model's inputs, tick the columns later steps depend on so missing
   values are caught, then **Validate**. Every later step reads the cleaned dataset, so
   include any column you will want to classify or stratify by.
2. **Building Characteristics**. Add the few characteristics that change energy use, such
   as age band, typology or heating system. For each one, set its values and how it is
   known:
   - **From my data**: a rule on a GIS column, for example year built mapped to age bands.
   - **Estimate it**: each simulated building draws a value from probabilities you set,
     optionally depending on other characteristics or GIS columns. You can start from an
     even split or estimate the table from a column that records the value for some
     buildings.

   Then choose which model parts each characteristic changes. **Check** validates;
   **Save & check library** saves and confirms that sampled combinations each find a record
   in the component library. **Inspect** follows one real building through the model.
   Column roles matched in GIS Cleaning (`Building_ID_col`, `Height_col`, `WWR_col`, ...)
   are written into `semantic-fields.yaml` on every save.
3. **Retrofits**. Bundle measures into packages, such as "oil boiler to heat pump where
   built before 1975". Each package is compared against the baseline. Use **Never
   downgrade** to order a characteristic's values from worst to best, so measures only
   move buildings towards the better values.
4. **Sampling**. Choose which buildings to simulate (all, a random subset, or a number per
   combination of characteristics) and how many draws of the estimated characteristics
   each one gets. **Write sampled buildings** writes `gis/buildings-sampled.geojson`, one
   row per building and draw, so globi can run estimated characteristics (it doesn't
   sample priors itself). The page shows the resulting number of simulations.
5. **Model Execution**. Review readiness for every step, then **Generate globi files**:
   `building.yml` for one building (`globi simulate`) and, once buildings are saved,
   `manifest.yml`, `artifacts.yml` and `gis-preprocessor.yml` for a batch run, each checked
   against globi's own models. The page prints the commands to run from the globi repo.
   **Export** downloads a JSON snapshot of the editors (not a globi file).

Three utility pages sit below the steps:

- **Component Library** lets you browse and edit the engineering records (lighting power,
  infiltration, HVAC efficiency, schedules) that model parts point to. A part picks a
  record by joining its characteristics' values with `_`, for example `SFH_pre_1975`.
  **Needed by the model** lists every record your characteristics and model parts require,
  with ✓/✕ and **+ Create**. Every type can be authored, including constructions (a layers
  editor: material and thickness, outside first); **Copy values from** and **Duplicate** start
  a record from an existing one. Its **Schedule variability** view sets seeded per-building noise on schedules, densities and
  setpoints (globi's `schedule_variability_config`).
- **Single Building** types every parameter of one building into globi's flat model and
  simulates it with `make cli simulate-flat` (EnergyPlus in Docker; the first run builds
  the image, which takes several minutes). The project must be inside the globi repo.
- **Project Files** lists every file in the project with its size and last-modified time,
  shows the contents of text files, and can load a saved artifact back into its editor.

### 3. Save and reload

**Save** on the Building Characteristics page writes every file with unsaved changes:
`semantic-fields.yaml`, `component-map.yaml` and `priors/priors.yaml`. **Revert** throws
away unsaved edits and re-reads the saved files. Saved work loads back into the editors
whenever the project is reopened, so closing the browser loses nothing that was saved.

Saving accepts half-finished work. Run **Check** separately to validate it.

### Help text

The sidebar's **Minimal** and **Explain** toggle controls the guidance. Minimal keeps it
behind the **?** next to each heading. Explain shows it under every section.

## Key concepts

**Deterministic characteristics** are derived from GIS columns by a rule, for example
`construction_year` mapped to `age_buckets` by numeric ranges, or a categorical column
grouped into fewer values. The values are added to the GIS data before simulation.

**Stochastic characteristics** are not in the GIS data, for example `heating_fuel`. They
need a prior distribution and are sampled at run time. One building can get different
values in different draws, which is how the model carries what the data does not record.

GloBI calls characteristics *semantic fields*, the probabilities *priors*, and the
mapping from characteristics to model parts the *component map*.

## Repository layout

```
sbem-ui/
├── web/                # Svelte frontend
│   ├── src/lib/
│   │   ├── workflows/  # one page per sidebar step
│   │   ├── components/ # shared UI components
│   │   ├── stores/     # Svelte stores
│   │   ├── api/        # backend client
│   │   ├── types/      # TypeScript types
│   │   └── help.ts     # help text shown in Explain mode
│   └── tests/          # frontend logic tests
├── server/             # FastAPI backend
│   ├── main.py
│   ├── routers/        # API endpoints
│   ├── services/       # business logic (workspace, GIS, priors, sampling, run files, jobs, LLM assist)
│   └── models/         # Pydantic models
├── lib/semantic_priors # vendored prior-tree library
├── templates/          # starter semantic fields, component maps, prior trees, project
│                       # templates (populated component library) and sample GIS
├── tests/              # Python tests
├── Makefile
└── pyproject.toml
```

## Status

The app is in early development. The workspace, GIS cleaning, building characteristics
(including priors and the sample preview), sampling, globi run-file generation and Single
Building runs work end to end. Retrofit packages are authored but not yet read by globi.
Still to come: authoring constructions (layers) in the component library, a generated
component map that needs no manual selectors, and running batch models from the UI.

## License

MIT
