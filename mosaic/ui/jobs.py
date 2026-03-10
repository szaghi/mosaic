"""Background job manager for long-running searches."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    status: str = "running"  # "running" | "done" | "error"
    result: Any = None
    error_message: str = ""
    progress: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the job finishes. Returns True if done, False on timeout."""
        return self._event.wait(timeout=timeout)


class JobManager:
    _MAX_AGE = 300  # seconds — purge completed jobs older than this

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        self._cleanup()
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id)
        with self._lock:
            self._jobs[job_id] = job
        future = self._executor.submit(fn, *args, **kwargs)
        future.add_done_callback(lambda f: self._on_complete(job_id, f))
        return job_id

    def _on_complete(self, job_id: str, future: Future) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            try:
                job.result = future.result()
                job.status = "done"
            except Exception as e:
                job.status = "error"
                job.error_message = str(e)
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
                jid for jid, j in self._jobs.items()
                if j.status != "running" and (now - j.created_at) > self._MAX_AGE
            ]

    def _cleanup(self) -> None:
        """Remove stale finished jobs to prevent unbounded memory growth."""
        stale = self.stale_job_ids()
        if not stale:
            return
        with self._lock:
            for jid in stale:
                self._jobs.pop(jid, None)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
