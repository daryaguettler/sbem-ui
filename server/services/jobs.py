"""Background jobs: run a command in a thread and read its JSON result back.

Used for runs that take minutes (Single Building's `make cli simulate-flat`). Each call is a
job with an id the frontend polls. Jobs live in this process's memory, so a backend restart
forgets them. Cloud credentials are stripped from the job's environment: runs started here are
local only.
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

#: Env vars never passed to a job (runs started from the UI are local only).
_CLOUD_ENV = re.compile(r"^(AWS_|HATCHET_CLIENT_|SCYTHE_STORAGE_)")


class JobError(Exception):
    """The job can't be started or found."""


@dataclass
class Job:
    """One background command."""

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


def _last_json_line(stdout: str) -> Any:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON output")


def _run(job: Job, cmd: list[str], cwd: Path, timeout: int) -> None:
    env = {k: v for k, v in os.environ.items() if not _CLOUD_ENV.match(k)}
    env.pop("VIRTUAL_ENV", None)  # sbem-ui's own venv must not leak into the command's
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


def start_command(command: str, cmd: list[str], cwd: Path, timeout: int) -> Job:
    """Run `cmd` in the background as job `command`, whose last stdout line is JSON."""
    with _LOCK:
        if any(j.command == command and j.status == "running" for j in _JOBS.values()):
            raise JobError(f"A {command} job is already running.")
        job = Job(id=uuid.uuid4().hex[:12], command=command)
        _JOBS[job.id] = job
    threading.Thread(target=_run, args=(job, cmd, cwd, timeout), daemon=True).start()
    return job


def get_job(job_id: str) -> Job:
    """A job by id."""
    job = _JOBS.get(job_id)
    if job is None:
        raise JobError(f"No job {job_id!r}.")
    return job
