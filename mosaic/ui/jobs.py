"""Background job manager for long-running searches."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Job:
    id: str
    status: str = "running"  # "running" | "done" | "error"
    result: Any = None
    error_message: str = ""
    progress: dict[str, str] = field(default_factory=dict)
    # Per-job UI state (form options, exportable results, …).  Lives and dies
    # with the job, so nothing leaks when finished jobs are purged.
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the job finishes. Returns True if done, False on timeout."""
        return self._event.wait(timeout=timeout)


class JobManager:
    _MAX_AGE = 900  # seconds — purge completed jobs older than this

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(
        self, fn: Callable, *args: Any, meta: dict[str, Any] | None = None, **kwargs: Any
    ) -> str:
        self.purge_stale()
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, meta=dict(meta or {}))
        with self._lock:
            self._jobs[job_id] = job
        future = self._executor.submit(fn, *args, **kwargs)
        future.add_done_callback(lambda f: self._on_complete(job_id, f))
        return job_id

    def register_done(self, result: Any = None, meta: dict[str, Any] | None = None) -> str:
        """Record an already-finished job (e.g. a synchronous cache search).

        The job is purged like any other, so data attached to it does not leak.
        """
        self.purge_stale()
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, status="done", result=result, meta=dict(meta or {}))
        job._event.set()
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def _on_complete(self, job_id: str, future: Future) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            try:
                job.result = future.result()
                job.status = "done"
            # BaseException: library code (or a dependency) may raise SystemExit;
            # anything that escapes here would leave the job "running" forever
            # and the UI polling it indefinitely.
            except BaseException as e:
                job.status = "error"
                if isinstance(e, SystemExit):
                    job.error_message = f"Operation aborted (exit status {e.code})."
                else:
                    job.error_message = str(e) or type(e).__name__
            job._event.set()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def pop(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.pop(job_id, None)

    def stale_job_ids(self) -> list[str]:
        """Return IDs of completed/errored jobs older than _MAX_AGE."""
        now = time.monotonic()
        with self._lock:
            return [
                jid
                for jid, j in self._jobs.items()
                if j.status != "running" and (now - j.created_at) > self._MAX_AGE
            ]

    def purge_stale(self) -> None:
        """Remove stale finished jobs to prevent unbounded memory growth."""
        stale = self.stale_job_ids()
        if not stale:
            return
        with self._lock:
            for jid in stale:
                self._jobs.pop(jid, None)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
