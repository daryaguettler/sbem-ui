# SBEM UI

Svelte-based UI for creating SBEM (Simplified Building Energy Model) artifacts without writing YAML.

## Overview

This application enables non-technical users to create building energy modeling artifacts through a visual interface:

- **Semantic Fields**: Define deterministic and stochastic semantic fields from GIS data
- **Component Maps**: Link semantic fields to building components
- **Prior Trees**: Generate prior distributions for stochastic semantic fields,
  conditioned on any combination of GIS columns and semantic fields
- **GIS Cleaning**: Validate and preprocess GIS building data
- **Model Execution**: Run deterministic and stochastic building energy models (future)

## Architecture

- **Frontend**: Svelte 5 + TypeScript + Vite
- **Backend**: FastAPI (Python)
- **Visualization**: @xyflow/svelte for graph-based interfaces
- **Integration**: Direct dependency on `epinterface` (the real component graph +
  Prisma-backed SQLite component library used by `globi`) and `semantic-priors`
  (prior-tree schema + sampling engine). See "Backend Setup" below for the extra
  Prisma codegen step this requires.
- **Persistence**: A "project workspace" is a directory on disk (semantic fields,
  component map, a real `components-lib.db`, GIS files, priors) that the backend
  reads/writes -- there's no separate database server. Pick or create one from the
  UI on first load; it's remembered in the browser so reopening the app reopens
  the same project.

## Saving and reloading your work

Every editor has a **Save to project** button next to its **Export YAML** button. Export
downloads the artifact; save writes that same document into the project directory
(`semantic-fields.yaml`, `component-map.selectors.yaml`, `priors/priors.yaml`) instead.

Saved artifacts are loaded straight back into the editors whenever the project is
reopened, so closing the browser doesn't lose anything. Two ways to reload on demand:

- **Revert to saved** in an editor's toolbar throws away unsaved edits and re-reads that
  editor's file.
- **Project Files** in the sidebar lists every file in the project directory with its size
  and last-modified time, shows the contents of any text file, and offers **Load into
  editor** for the three saved artifacts.

Saving is deliberately lenient -- half-finished work is worth keeping, so validation stays
a separate button.

## Project Structure

```
sbem-ui/
├── web/                    # Svelte frontend
│   ├── src/
│   │   ├── lib/
│   │   │   ├── components/  # Reusable UI components
│   │   │   ├── workflows/   # Workflow-specific pages
│   │   │   ├── stores/      # Svelte stores for state
│   │   │   ├── types/       # TypeScript types
│   │   │   └── utils/       # Helper functions
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
├── server/                 # FastAPI backend
│   ├── main.py
│   ├── routers/            # API endpoints
│   ├── services/           # Business logic
│   └── models/             # Pydantic models
├── templates/              # Pre-built artifact templates
│   ├── semantic_fields/
│   ├── component_maps/
│   └── prior_trees/
├── lib/                    # Shared Python utilities
├── pyproject.toml
└── README.md
```

## Development Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- uv (recommended) or pip

### Frontend Setup

```bash
cd web
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`

### Backend Setup

No other checkouts are needed. `epinterface` installs from GitHub (the same branch
globi pins), and `semantic_priors` is vendored in `lib/semantic_priors` (see its
`VENDORED.md`).

```bash
# Install Python dependencies (pulls in epinterface and prisma)
uv sync

# One-time: generate the Prisma Python client from epinterface's schema.
# This downloads platform-specific query-engine binaries from Prisma's CDN,
# so it needs network access; it will fail cryptically in restricted
# environments (see epinterface's own `epinterface prisma generate` for the
# underlying command if you need to run it outside this venv).
uv run epinterface prisma generate

# Run the backend server
cd server
uv run python main.py
```

The backend API will be available at `http://localhost:8000`. On first load the
frontend will prompt you to create or open a project workspace -- creating one
also provisions that project's `components-lib.db` (runs `prisma migrate
deploy` against a fresh SQLite file), which takes a couple of seconds.

### API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation.

## Current Status

### Architecture Phase 0: Foundations ✅
- ✅ Real dependency on `epinterface` (component graph + Prisma SQLite component
  library) and `semantic-priors` (prior schema + sampling engine)
- ✅ File-backed project workspace (`server/services/workspace.py`) replacing
  in-memory-only state; GIS session migrated onto it
- ✅ `GET /api/component-tree/` serves the real, live `epinterface` component
  graph -- the frontend's previously-hardcoded `prismaComponents.ts` is gone
- ✅ Editors save into the project directory and reload from it (`/api/artifacts`),
  plus a Project Files browser for everything on disk
- ⏳ Component library authoring, generated component-map, native prior editor
  (see the architecture plan for the full phased breakdown)

### Phase 1: Foundation ✅
- ✅ Svelte + Vite project structure
- ✅ FastAPI backend with basic routing
- ✅ Template system structure
- ✅ Basic UI layout with sidebar navigation
- ✅ Template loading and display functionality

### Phase 2: Semantic Fields Editor - Deterministic 🔄 IN PROGRESS
- ✅ Template system with semantic field templates
- ✅ Semantic fields store with state management
- ✅ Template loading and conversion to frontend format
- ✅ Basic semantic fields display UI
- ✅ Deterministic vs stochastic field distinction
- ⏳ Numeric range mapping editor
- ⏳ Categorical grouping editor
- ⏳ Compound field builder
- ⏳ Transformation preview panel
- ⏳ GIS data upload and column exploration

### Phase 5: Prior Tree Editor ✅
- ✅ Priors authored as a real `semantic_priors` `RegionConfig`
  (`registry`/`priors`/`joints`/`scenarios`), validated by that library's own models
- ✅ Condition a prior on any combination of semantic fields and raw GIS columns
- ✅ Generate the lookup table from the project's GIS rows — evenly, or estimated
  from a column that already records the field for some buildings
- ✅ Editable heatmap of the table, with per-row provenance and a fallback
- ✅ Conditioned *numeric* priors: one clipped normal per combination, fitted from
  the data and edited as a dot plot (these live in `priors` as a `ConditionalPrior`
  plus its compound key, since `joints` only compiles to categorical samplers)
- ✅ Scenario editor: fixed and conditional overrides (`$keep` / `$OtherField`),
  validated against the declared domains
- ✅ Sampling-order graph, a sample preview over the project's own stock, and a
  baseline-vs-scenario comparison drawn from one shared sample

### Remaining Phases
- Phase 3: Semantic Fields Editor - Stochastic
- Phase 4: Component Map Editor
- Phase 6: GIS Cleaning Interface
- Phase 7: Validation & Export
- Phase 8: Model Execution (future)

## Key Features

### Deterministic vs Stochastic Semantic Fields

**Deterministic Semantic Fields**:
- Derived from existing GIS columns using transformation rules
- Examples: `construction_year` → `age_buckets` (numeric range mapping)
- Transformation rules applied directly to GIS data
- New columns added to GIS data before simulation

**Stochastic Semantic Fields**:
- Don't exist in GIS data (no clear transformation rule)
- Examples: `heating_fuel` (user doesn't have deterministic data)
- Require prior distributions for runtime sampling
- Tagged as stochastic, sampled during simulation runs

## Templates

The project includes pre-built templates for common scenarios:

- **Semantic Fields**: Residential deterministic and stochastic field templates
- **Component Maps**: Standard residential component hierarchy
- **Prior Trees**: Heating system priors for residential buildings

## Contributing

This project is currently in early development. Please refer to the implementation plan for detailed phase information.

## License

MIT License