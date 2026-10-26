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
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Network access for the first setup (`epinterface` installs from GitHub and Prisma
  downloads its query-engine binaries)

### Install

```bash
make setup
```

This runs three steps, which you can also run yourself:

```bash
uv sync                          # Python deps, including epinterface and prisma
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
the directory and provisions its `components-lib.db`, which takes a few seconds. Use
**Switch project** at the bottom of the sidebar to change projects later.

A project looks like this on disk:

```
<project>/
├── project.json                  # name, created date, schema version
├── gis/                          # uploaded GIS file, cleaned data, column mappings
├── semantic-fields.yaml          # building characteristics
├── component-map.selectors.yaml  # which characteristics choose each model part
├── component-map.yaml            # generated component map
├── components-lib.db             # component library (epinterface schema)
└── priors/priors.yaml            # estimates for characteristics not in your data
```

`project.json` can remap any of these paths with a `"files"` map, so an existing repo
layout (such as norway-globi's `inputs/` folder) can be opened as a project. An optional
`"runner"` entry points at a repo whose `norway` CLI the app uses to validate inputs and
run local test simulations.

### 2. Work through the steps

The sidebar lists the steps in order. A step shows a check once its readiness checks pass;
hover over it to see what is missing.

1. **GIS Cleaning**. Upload a CSV or GeoJSON with one row per building. Match your
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

   Then choose which model parts each characteristic changes. **Check** saves and
   confirms that sampled combinations each find a record in the component library.
   **Inspect** follows one real building through the model.
3. **Retrofits**. Bundle measures into packages, such as "oil boiler to heat pump where
   built before 1975". Each package is compared against the baseline. Use **Never
   downgrade** to order a characteristic's values from worst to best, so measures only
   move buildings towards the better values.
4. **Sampling**. Choose how many buildings to simulate for training and how to stratify
   them, and how to split the stock into prediction jobs (for example by municipality).
   The page shows the estimated number of simulations and their cost.
5. **Model Execution**. Review readiness for every step. If the project has a runner,
   validate the inputs and run a small local test to sanity-check EUI and savings.
   **Export** downloads a JSON snapshot of the project for sharing or archiving. It is
   not a GloBI `manifest.yml`.

Two utility pages sit below the steps:

- **Component Library** lets you browse and edit the engineering records (lighting power,
  infiltration, HVAC efficiency, schedules) that model parts point to. A part picks a
  record by joining its characteristics' values with `_`, for example `SFH_pre_1975`.
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
│   ├── services/       # business logic (workspace, GIS, priors, runner, LLM assist)
│   └── models/         # Pydantic models
├── lib/semantic_priors # vendored prior-tree library
├── templates/          # starter semantic fields, component maps and prior trees
├── tests/              # Python tests
├── Makefile
└── pyproject.toml
```

## Status

The app is in early development. The workspace, GIS cleaning, building characteristics
(including priors, scenarios and the sample preview), retrofits, sampling and local test
runs work end to end. Still to come: authoring the component library from scratch, a
generated component map that needs no manual selectors, and running full models from the
UI.

## License

MIT
