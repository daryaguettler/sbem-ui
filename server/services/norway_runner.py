"""Run a project's `norway` CLI (norway-globi) in the background and read its JSON back.

sbem-ui never imports globi: validation, retrofit previews, sampling estimates and local
test runs all go through the runner repo named in `project.json` (`"runner": ".."`), as
``uv run --project <runner> norway <command> ... --json``. Each call is a job with an id
the frontend polls, because a validation or a test run takes tens of seconds to minutes.

Test runs are always small and local: `MAX_TEST_BUILDINGS` is enforced here as well as
by norway-globi itself, and the runner strips every cloud credential from its process.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

MAX_TEST_BUILDINGS = 25
MAX_TEST_SAMPLES = 3

#: command -> (argv after `norway`, timeout seconds)
COMMANDS: dict[str, tuple[list[str], int]] = {
    "validate": (["validate", "--json"], 900),
    "retrofit-preview": (["retrofits", "preview", "--json"], 600),
    "sampling": (["sampling", "--json"], 600),
    "test-run": (["test-run", "--json"], 3600),
}

#: Env vars never passed to a runner job (test runs are local only).
_CLOUD_ENV = re.compile(r"^(AWS_|HATCHET_CLIENT_|SCYTHE_STORAGE_)")


class RunnerError(Exception):
    """The project has no runner, or the request is not allowed."""


@dataclass
class Job:
    """One background `norway` call."""

    id: str
    command: str
    status: str = "running"  # running | done | failed
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: Any = None
    error: str | None = None
    log: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "status": self.status,
            "startedAt": self.started_at,
            "result": self.result,
            "error": self.error,
            "log": self.log[-4000:],
        }


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def runner_status(runner: Path | None) -> dict[str, Any]:
    """Whether the project has a usable runner repo."""
    available = bool(runner and (runner / "pyproject.toml").exists())
    return {"runner": str(runner) if runner else None, "available": available}


def build_argv(command: str, options: dict[str, Any]) -> list[str]:
    """`norway` argv for one command, with the test-run caps enforced."""
    if command not in COMMANDS:
        raise RunnerError(f"Unknown command {command!r}.")
    argv = list(COMMANDS[command][0])
    if command == "test-run":
        n = int(options.get("n", 10))
        samples = int(options.get("samples", 1))
        if not 1 <= n <= MAX_TEST_BUILDINGS:
            raise RunnerError(f"Test runs use 1-{MAX_TEST_BUILDINGS} buildings.")
        if not 1 <= samples <= MAX_TEST_SAMPLES:
            raise RunnerError(f"Test runs use 1-{MAX_TEST_SAMPLES} draws per building.")
        packages = [str(p) for p in options.get("packages") or []]
        argv += ["--n", str(n), "--samples", str(samples)]
        argv += ["--packages", *(packages or ["all"])]
    if command == "validate" and options.get("skip_components"):
        argv.append("--skip-components")
    return argv


def _last_json_line(stdout: str) -> Any:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON output")


def _run(job: Job, cmd: list[str], cwd: Path, timeout: int) -> None:
    env = {k: v for k, v in os.environ.items() if not _CLOUD_ENV.match(k)}
    env.pop("VIRTUAL_ENV", None)  # sbem-ui's own venv must not leak into the runner's
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
        )
        job.log = proc.stderr
        try:
            job.result = _last_json_line(proc.stdout)
        except ValueError:
            job.result = None
        if job.result is None:
            job.status = "failed"
            job.error = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        elif isinstance(job.result, dict) and job.result.get("error"):
            job.status = "failed"
            job.error = str(job.result["error"])
        else:
            job.status = "done"
    except subprocess.TimeoutExpired:
        job.status = "failed"
        job.error = f"timed out after {timeout // 60} min"
    except FileNotFoundError:
        job.status = "failed"
        job.error = f"`{cmd[0]}` is not on PATH"


def start_job(runner: Path | None, command: str, options: dict[str, Any]) -> Job:
    """Start one background job; one job per command at a time."""
    if not runner_status(runner)["available"]:
        raise RunnerError("This project has no runner repo (set \"runner\" in project.json).")
    argv = build_argv(command, options)
    assert runner is not None
    cmd = ["uv", "run", "--project", str(runner), "norway", *argv]
    return start_command(command, cmd, runner, COMMANDS[command][1])


def start_command(command: str, cmd: list[str], cwd: Path, timeout: int) -> Job:
    """Run `cmd` in the background as job `command`, whose last stdout line is JSON."""
    with _LOCK:
        if any(j.command == command and j.status == "running" for j in _JOBS.values()):
            raise RunnerError(f"A {command} job is already running.")
        job = Job(id=uuid.uuid4().hex[:12], command=command)
        _JOBS[job.id] = job
    threading.Thread(target=_run, args=(job, cmd, cwd, timeout), daemon=True).start()
    return job


def get_job(job_id: str) -> Job:
    """A job by id."""
    job = _JOBS.get(job_id)
    if job is None:
        raise RunnerError(f"No job {job_id!r}.")
    return job


# =============================================================================
# sampling settings: single keys of training.yml / inference.yml, edited in place
# =============================================================================


def _value(value: Any) -> str:
    return json.dumps(value) if not isinstance(value, str) else value


def set_yaml_key(text: str, key: str, value: Any, *, parent: str | None = None) -> str:
    """Replace ``key: ...`` (top level, or one level under `parent`) keeping comments.

    Values are written in flow style (``[a, b]`` / ``{}`` / scalars). A missing key is
    appended (under `parent`, created if needed).
    """
    rendered = "null" if value is None else _value(value)
    if isinstance(value, list):
        rendered = "[" + ", ".join(_value(v) for v in value) + "]"
    indent = "  " if parent else ""
    pattern = re.compile(rf"^{indent}{re.escape(key)}:[^\n]*$", re.M)
    if parent:
        block = re.search(rf"^{re.escape(parent)}:\s*\n((?:[ \t]+[^\n]*\n?|\s*\n)*)", text, re.M)
        if block is None:
            return text.rstrip("\n") + f"\n{parent}:\n{indent}{key}: {rendered}\n"
        body = block.group(1)
        new_body, n = pattern.subn(f"{indent}{key}: {rendered}", body, count=1)
        if not n:
            new_body = body.rstrip("\n") + f"\n{indent}{key}: {rendered}\n"
        return text[: block.start(1)] + new_body + text[block.end(1) :]
    new, n = pattern.subn(f"{key}: {rendered}", text, count=1)
    return new if n else text.rstrip("\n") + f"\n{key}: {rendered}\n"


SAMPLING_KEYS = {
    "training": {
        "n_per_iter": None,
        "min_per_stratum": None,
        "max_iters": None,
        "strata_fields": "norway_training",
        "strata_bins": "norway_training",
        "context_per_stratum": "norway_training",
    },
    "inference": {"partition_field": None, "n_samples": None, "packages": None},
}


def read_sampling(training: Path, inference: Path) -> dict[str, Any]:
    """The sampling settings the Sampling page edits."""
    t = yaml.safe_load(training.read_text()) if training.exists() else {}
    i = yaml.safe_load(inference.read_text()) if inference.exists() else {}
    t, i = t or {}, i or {}
    block = t.get("norway_training") or {}
    return {
        "n_per_iter": t.get("n_per_iter"),
        "min_per_stratum": t.get("min_per_stratum"),
        "max_iters": t.get("max_iters"),
        "strata_fields": block.get("strata_fields", []),
        "strata_bins": block.get("strata_bins", {}),
        "context_per_stratum": block.get("context_per_stratum"),
        "partition_field": i.get("partition_field"),
        "n_samples": i.get("n_samples"),
        "packages": i.get("packages", "all"),
    }


def write_sampling(training: Path, inference: Path, settings: dict[str, Any]) -> None:
    """Write the given settings back, key by key, keeping the files' comments."""
    for path, keys in ((training, SAMPLING_KEYS["training"]), (inference, SAMPLING_KEYS["inference"])):
        wanted = {k: settings[k] for k in keys if k in settings}
        if not wanted:
            continue
        text = path.read_text() if path.exists() else ""
        for key, value in wanted.items():
            text = set_yaml_key(text, key, value, parent=keys[key])
        yaml.safe_load(text)  # never write a file that no longer parses
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
