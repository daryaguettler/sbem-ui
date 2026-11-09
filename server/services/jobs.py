"""Background jobs: run a command in a thread and read its JSON result back.

Used for runs that take minutes (Single Building, and Model Execution's globi runs). Each call is a
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
from collections.abc import Callable
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
    #: What a multi-step task is doing now, for the page to show.
    stage: str = ""
    #: Where a task mirrors its state, so a reloaded page, or a restarted backend, can show it.
    record: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "status": self.status,
            "startedAt": self.started_at,
            "result": self.result,
            "error": self.error,
            "log": self.log[-4000:],
            "stage": self.stage,
        }

    def save(self) -> None:
        """Write the state to `record` (with this backend's pid, to spot a restart)."""
        if self.record is not None:
            self.record.parent.mkdir(parents=True, exist_ok=True)
            self.record.write_text(json.dumps({**self.as_dict(), "pid": os.getpid()}))

    def set_stage(self, stage: str) -> None:
        self.stage = stage
        self.save()


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def _last_json_line(stdout: str) -> Any:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON output")


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not _CLOUD_ENV.match(k)}
    env.pop("VIRTUAL_ENV", None)  # sbem-ui's own venv must not leak into the command's
    return env


def _run(job: Job, cmd: list[str], cwd: Path, timeout: int) -> None:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, cwd=cwd, env=_env(), capture_output=True, text=True, timeout=timeout
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


def _new_job(command: str) -> Job:
    with _LOCK:
        if any(j.command == command and j.status == "running" for j in _JOBS.values()):
            raise JobError(f"A {command} job is already running.")
        job = Job(id=uuid.uuid4().hex[:12], command=command)
        _JOBS[job.id] = job
    return job


def start_command(command: str, cmd: list[str], cwd: Path, timeout: int) -> Job:
    """Run `cmd` in the background as job `command`, whose last stdout line is JSON."""
    job = _new_job(command)
    threading.Thread(target=_run, args=(job, cmd, cwd, timeout), daemon=True).start()
    return job


class StepFailed(Exception):
    """One command of a task failed; the message says why, for the page."""


def run_step(job: Job, cmd: list[str], cwd: Path, timeout: int) -> str:
    """Run one command of a task and return its stdout; its output is appended to the job log."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, cwd=cwd, env=_env(), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise StepFailed(f"timed out after {timeout // 60} min") from exc
    except FileNotFoundError as exc:
        raise StepFailed(f"`{cmd[0]}` is not on PATH") from exc
    job.log += proc.stderr + proc.stdout
    if proc.returncode != 0:
        lines = [line for line in (proc.stderr + proc.stdout).splitlines() if line.strip()]
        # make's own "*** [target] Error 1" line says nothing; report the command's last words
        cause = [line for line in lines if not line.startswith("make")]
        raise StepFailed((cause or lines or ["no output"])[-1].strip())
    return proc.stdout


def start_task(command: str, work: Callable[[Job], Any], record: Path | None = None) -> Job:
    """Run `work(job)` in the background as job `command`; its return value is the result.
    With `record`, the job's state is saved there as it changes (read it with read_record)."""
    job = _new_job(command)
    job.record = record
    job.save()

    def target() -> None:
        try:
            job.result = work(job)
            job.status = "done"
        except Exception as exc:  # any failure is reported on the page, not raised in a thread
            job.status = "failed"
            job.error = str(exc) or type(exc).__name__
        job.save()

    threading.Thread(target=target, daemon=True).start()
    return job


def read_record(path: Path) -> dict[str, Any] | None:
    """A task's last saved state. One still 'running' that this backend isn't running (it
    restarted mid-run) reads as interrupted: nothing will update it any more."""
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    if state.get("status") == "running" and (state.get("pid") != os.getpid() or state.get("id") not in _JOBS):
        state.update(status="interrupted", error="The backend restarted during this run, so its progress was lost. Run it again.")
    return state


def get_job(job_id: str) -> Job:
    """A job by id."""
    job = _JOBS.get(job_id)
    if job is None:
        raise JobError(f"No job {job_id!r}.")
    return job
