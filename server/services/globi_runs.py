"""Run globi from Model Execution: the form's building, or a random sample of the stock.

Both go through globi's own `make cli-native` (globi's venv and its .env.local.host.* files, so
EnergyPlus runs natively and the batch talks to the local Hatchet and storage started by
`make hatchet-token` / `make engine`). Results are read from the files globi saves:
`<output-dir>/results/EnergyAndPeak.parquet` for one building, and the `EnergyAndPeak.pq`
that `globi get experiment` downloads for a batch.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from services.globi_run_files import globi_root, saved_gis
from services.jobs import Job, StepFailed, read_record, run_step, start_task
from services.workspace import ProjectWorkspace

BUILDING_TIMEOUT = 15 * 60
FETCH_TIMEOUT = 10 * 60
SAMPLE_SEED = 0
#: Index levels of a batch result that describe the building (semantic fields are prefixed).
SEMANTIC_PREFIX = "feature.semantic."
AREA = "feature.geometry.energy_model_conditioned_area"
ENGINE_HINT = "Is globi's engine running? In the globi folder: make hatchet-token, then make engine."
#: Failures that mean Hatchet or local storage can't be reached, rather than a broken run.
UNREACHABLE = re.compile(r"connect|refused|unavailable|deadline exceeded|timed out", re.IGNORECASE)


def _record(workspace: ProjectWorkspace, command: str) -> Path:
    return workspace.root / "runs" / f"{command}.json"


def latest_runs(workspace: ProjectWorkspace) -> dict[str, Any]:
    """The project's last run of each kind, as saved while it ran (None if never run)."""
    return {"building": read_record(_record(workspace, "globi-building")), "sample": read_record(_record(workspace, "globi-sample"))}


class GlobiRunError(Exception):
    """The run can't start (the message says what to do first)."""


# -- reading results -------------------------------------------------------------------


def end_uses(df: pd.DataFrame) -> pd.DataFrame:
    """kWh/m² per end use (columns) for each simulated building (rows), summed over months."""
    return df["Energy"]["End Uses"].T.groupby(level="Meter").sum().T


def peaks(df: pd.DataFrame) -> pd.DataFrame:
    """Peak kW/m² per utility (columns) for each building (rows), as globi's summary sums them."""
    return df["Peak"]["Utilities"].T.groupby(level="Meter").sum().T


def summarize_building(path: Path) -> dict[str, Any]:
    """One building's end uses and peaks, as Single Building shows them."""
    df = pd.read_parquet(path)
    return {
        "end_uses_kwh_m2": end_uses(df).iloc[0].astype(float).to_dict(),
        "peak_kw_m2": peaks(df).iloc[0].astype(float).to_dict(),
        "output_dir": str(path.parent.parent),
    }


def summarize_stock(path: Path) -> dict[str, Any]:
    """A batch's buildings and their floor-area-weighted mean end uses (kWh/m² of the sample)."""
    df = pd.read_parquet(path)
    uses = end_uses(df)
    index = df.index.to_frame(index=False)
    area = index[AREA].astype(float) if AREA in index else pd.Series(1.0, index=index.index)
    weights = area.to_numpy()
    mean = (uses.mul(weights, axis=0).sum() / weights.sum()).astype(float).to_dict()
    semantic = [c for c in index.columns if c.startswith(SEMANTIC_PREFIX)]
    buildings = [
        {
            "building_id": str(index.at[i, "building_id"]) if "building_id" in index else str(i),
            "area_m2": float(area.iloc[i]),
            "values": {c.removeprefix(SEMANTIC_PREFIX): str(index.at[i, c]) for c in semantic},
            "end_uses_kwh_m2": uses.iloc[i].astype(float).to_dict(),
        }
        for i in range(len(index))
    ]
    return {"mean_kwh_m2": mean, "buildings": buildings, "results_file": str(path)}


# -- one building ----------------------------------------------------------------------


def start_building_run(workspace: ProjectWorkspace) -> Job:
    """Simulate the project's building.yml (written by Generate globi files) in the background."""
    building = workspace.path("building")
    if not building.exists():
        raise GlobiRunError("Generate globi files first: the run uses building.yml.")
    context = (yaml.safe_load(building.read_text()) or {}).get("semantic_field_context") or {}
    output_dir = workspace.root / "outputs" / "building"
    results = output_dir / "results" / "EnergyAndPeak.parquet"
    globi = globi_root()

    def work(job: Job) -> dict[str, Any]:
        results.unlink(missing_ok=True)  # never report a previous run's numbers
        job.set_stage("Simulating the building")
        run_step(job, ["make", "cli-native", "simulate", "--", "--config", str(building.resolve()), "--output-dir", str(output_dir)], globi, BUILDING_TIMEOUT)
        return {**summarize_building(results), "context": context}

    return start_task("globi-building", work, _record(workspace, "globi-building"))


# -- a random sample of the stock ------------------------------------------------------


def scenario_manifests(workspace: ProjectWorkspace) -> dict[str, Path]:
    """The batch manifests Generate globi files wrote, by the Scenario each runs."""
    first = workspace.path("manifest")
    found: dict[str, Path] = {}
    for path in [first, *sorted(first.parent.glob("manifest-*.yml"))]:
        if path.exists():
            found[str((yaml.safe_load(path.read_text()) or {}).get("scenario", "Baseline"))] = path
    return found


def prepare_sample(workspace: ProjectWorkspace, n: int, scenarios: list[str]) -> tuple[Path, dict[str, Path], int]:
    """Write `runs/sample-<n>/`: n random buildings and one manifest per scenario that runs them.

    Every scenario runs the same buildings, so before and after compare like with like.
    -> (run folder, manifest per scenario, buildings in the sample)
    """
    if n < 1:
        raise GlobiRunError("Choose at least 1 building.")
    gis = saved_gis(workspace)
    manifests = scenario_manifests(workspace)
    if gis is None or not manifests or not workspace.path("artifacts").exists():
        raise GlobiRunError(
            "Generate globi files with saved buildings first (Sampling → Write sampled buildings, then Generate globi files)."
        )
    unknown = [s for s in scenarios if s not in manifests]
    if unknown or not scenarios:
        raise GlobiRunError(f"Choose scenarios from: {', '.join(manifests)}.")

    stock = json.loads(gis.read_text())
    features = stock.get("features") or []
    if not features:
        raise GlobiRunError(f"{gis.name} has no buildings.")
    picked = random.Random(SAMPLE_SEED).sample(features, min(n, len(features)))

    run_dir = workspace.root / "runs" / f"sample-{n}"
    run_dir.mkdir(parents=True, exist_ok=True)
    sample_gis = run_dir / "buildings.geojson"
    sample_gis.write_text(json.dumps({**stock, "features": picked}))
    artifacts = yaml.safe_load(workspace.path("artifacts").read_text())
    artifacts_path = run_dir / "artifacts.yml"
    artifacts_path.write_text(yaml.safe_dump({**artifacts, "gis_file": str(sample_gis.resolve())}, sort_keys=False))

    written: dict[str, Path] = {}
    for scenario in scenarios:
        manifest = yaml.safe_load(manifests[scenario].read_text())
        manifest.update(name=f"{manifest['name']}-sample", scenario=scenario, file_config=str(artifacts_path.resolve()))
        slug = "".join(c if c.isalnum() else "-" for c in scenario).strip("-").lower()
        written[scenario] = run_dir / f"manifest-{slug}.yml"
        written[scenario].write_text(yaml.safe_dump(manifest, sort_keys=False))
    return run_dir, written, len(picked)


def start_sample_run(workspace: ProjectWorkspace, n: int, scenarios: list[str]) -> Job:
    """Simulate n random buildings under each scenario on globi's local Hatchet, in the background."""
    run_dir, manifests, count = prepare_sample(workspace, n, scenarios)
    globi = globi_root()
    # shortcut: a fixed allowance per building, assuming a few worker slots; raise it for slow machines
    poll_timeout = 600 + 30 * count

    def work(job: Job) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for scenario, manifest in manifests.items():
            job.set_stage(f"{scenario}: simulating {count} building{'s' if count != 1 else ''}")
            # globi's e2e command submits the manifest and waits for Hatchet, then prints RUN_NAME=
            cmd = ["make", "cli-native", "tests", "e2e", "--", "--manifest", str(manifest), "--max-sims", str(count),
                   "--poll-timeout", str(poll_timeout), "--poll-interval", "10"]
            try:
                stdout = run_step(job, cmd, globi, poll_timeout + 300)
            except StepFailed as exc:
                hint = f" {ENGINE_HINT}" if UNREACHABLE.search(str(exc)) else " The job log in runs/globi-sample.json has the details."
                raise StepFailed(f"{scenario}: {exc}.{hint}") from exc
            found = re.search(r"^RUN_NAME=(.+)$", stdout, re.MULTILINE)
            if not found:
                raise StepFailed(f"{scenario}: globi finished without naming the run. {ENGINE_HINT}")
            run_name = found.group(1).strip()

            job.set_stage(f"{scenario}: fetching results")
            fetched = run_dir / "results"
            run_step(job, ["make", "cli-native", "get", "experiment", "--", "--run-name", run_name, "--output-dir", str(fetched)], globi, FETCH_TIMEOUT)
            files = sorted((fetched / run_name).glob("*/EnergyAndPeak.pq"), key=lambda p: p.stat().st_mtime)
            if not files:
                raise StepFailed(f"{scenario}: no results were downloaded for {run_name}.")
            results[scenario] = {**summarize_stock(files[-1]), "run_name": run_name}
        return {"buildings": count, "run_dir": str(run_dir), "scenarios": results}

    return start_task("globi-sample", work, _record(workspace, "globi-sample"))
