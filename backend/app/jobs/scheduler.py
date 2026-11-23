"""Persistent scheduler and job runner.

* Schedules and jobs live in the database, so state survives restarts.
* Restart recovery: jobs left ``running`` by a previous process are re-queued
  (flagged ``recovered``); stuck jobs whose heartbeat expired are re-queued.
* Missed-job handling: if the host was off, overdue schedules are coalesced
  into ONE catch-up run and ``missed_runs`` is incremented.
* Retries with exponential backoff; non-retryable errors fail immediately.
* Cancellation: queued jobs cancel immediately; running jobs stop at the next
  cancellation checkpoint.
* A job is ``succeeded`` only when its handler returned normally.
"""
from __future__ import annotations

import logging
import socket
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Job, Notification, Schedule, WorkerHeartbeat

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class NonRetryable(Exception):
    pass


class Deferred(Exception):
    """Handler is not ready to run yet (e.g. waiting for research jobs); re-queue without using an attempt."""

    def __init__(self, seconds: int = 60, reason: str = ""):
        super().__init__(reason)
        self.seconds = seconds


class JobContext:
    def __init__(self, db: Session, job: Job):
        self.db = db
        self.job = job

    def check_cancel(self) -> None:
        cancelled = self.db.execute(select(Job.cancel_requested).where(Job.id == self.job.id)).scalar_one()
        if cancelled:
            raise JobCancelled()

    def heartbeat(self) -> None:
        self.db.execute(update(Job).where(Job.id == self.job.id).values(heartbeat_at=datetime.now(timezone.utc)))


Handler = Callable[[JobContext], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def handler(name: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn

    return deco


def backoff_seconds(attempt: int) -> int:
    return min(60 * 2 ** (attempt - 1), 3600)


def enqueue(db: Session, job_type: str, *, business_id: int | None = None, source_id: int | None = None,
            payload: dict | None = None, priority: int = 5, triggered_by: str = "owner", schedule_id: int | None = None,
            max_attempts: int = 4, dedupe: bool = True) -> Job:
    if dedupe:
        existing = db.execute(select(Job).where(Job.job_type == job_type, Job.business_id == business_id if business_id else Job.business_id.is_(None),
                                                Job.source_id == source_id if source_id else Job.source_id.is_(None),
                                                Job.status.in_(["queued", "running", "retry_wait"]))).scalars().first()
        if existing:
            return existing
    job = Job(job_type=job_type, business_id=business_id, source_id=source_id, payload=payload or {}, priority=priority,
              triggered_by=triggered_by, schedule_id=schedule_id, max_attempts=max_attempts)
    db.add(job)
    db.flush()
    return job


def cancel(db: Session, job: Job) -> Job:
    if job.status in ("queued", "retry_wait"):
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        job.error = "Cancelled by owner before start"
    elif job.status == "running":
        job.cancel_requested = True
    return job


class Scheduler:
    def __init__(self, session_factory=SessionLocal, worker_threads: int | None = None):
        s = get_settings()
        self.session_factory = session_factory
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.poll_seconds = s.scheduler_poll_seconds
        self.heartbeat_timeout = s.job_heartbeat_timeout_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=worker_threads or s.worker_threads, thread_name_prefix="exechub-job")
        self._running: set[int] = set()
        self._lock = threading.Lock()
        self.processed = 0

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.recover_on_startup()
        self._thread = threading.Thread(target=self._loop, name="exechub-scheduler", daemon=True)
        self._thread.start()

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._pool.shutdown(wait=wait, cancel_futures=True)
        with self.session_factory() as db:
            hb = db.get(WorkerHeartbeat, self.worker_id)
            if hb:
                hb.status = "stopped"
                db.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick(run_inline=False)
            except Exception:  # pragma: no cover - defensive
                log.exception("scheduler tick failed")
            self._stop.wait(self.poll_seconds)

    # ------------------------------------------------------------------ recovery
    def recover_on_startup(self) -> int:
        """Re-queue jobs that were running when the previous process stopped."""
        with self.session_factory() as db:
            n = 0
            for job in db.execute(select(Job).where(Job.status == "running")).scalars():
                job.status = "queued"
                job.recovered = True
                job.worker_id = None
                job.next_attempt_at = datetime.now(timezone.utc)
                job.error = (job.error or "") + " [recovered after restart]"
                n += 1
            if n:
                db.add(Notification(kind="system", severity="warning", title=f"Recovered {n} interrupted job(s) after restart",
                                    body="Jobs that were running when the app stopped were re-queued."))
            db.commit()
            return n

    def recover_stuck(self, db: Session) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.heartbeat_timeout)
        n = 0
        for job in db.execute(select(Job).where(Job.status == "running", Job.heartbeat_at < cutoff)).scalars():
            with self._lock:
                if job.id in self._running:
                    continue
            job.status = "queued"
            job.recovered = True
            job.error = (job.error or "") + " [heartbeat expired; re-queued]"
            n += 1
        return n

    # ------------------------------------------------------------------ schedules
    def enqueue_due(self, db: Session, now: datetime | None = None) -> list[Job]:
        now = now or datetime.now(timezone.utc)
        jobs = []
        for sch in db.execute(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)).scalars():
            interval = timedelta(minutes=max(1, sch.interval_minutes))
            lag = now - sch.next_run_at
            missed = int(lag / interval)
            if missed > 0:
                sch.missed_runs += missed  # host was off / busy: coalesce into one catch-up run
            job = enqueue(db, sch.job_type, business_id=sch.business_id, source_id=sch.source_id, payload=dict(sch.payload or {}),
                          triggered_by="schedule" if not missed else "schedule:catch_up", schedule_id=sch.id)
            sch.last_run_at = now
            sch.last_job_id = job.id
            sch.next_run_at = now + interval
            jobs.append(job)
        return jobs

    # ------------------------------------------------------------------ execution
    def _claim(self, db: Session, limit: int) -> list[int]:
        now = datetime.now(timezone.utc)
        ids = db.execute(select(Job.id).where(Job.status.in_(["queued", "retry_wait"]), Job.next_attempt_at <= now,
                                              Job.cancel_requested.is_(False))
                         .order_by(Job.priority.asc(), Job.id.asc()).limit(limit)).scalars().all()
        claimed = []
        for jid in ids:
            res = db.execute(update(Job).where(Job.id == jid, Job.status.in_(["queued", "retry_wait"]))
                             .values(status="running", worker_id=self.worker_id, started_at=now, heartbeat_at=now,
                                     attempts=Job.attempts + 1))
            if res.rowcount:
                claimed.append(jid)
        db.commit()
        return claimed

    def run_job(self, job_id: int) -> str:
        with self._lock:
            self._running.add(job_id)
        db = self.session_factory()
        try:
            job = db.get(Job, job_id)
            fn = HANDLERS.get(job.job_type)
            ctx = JobContext(db, job)
            try:
                if fn is None:
                    raise NonRetryable(f"No handler for job type '{job.job_type}'")
                result = fn(ctx) or {}
                db.commit()
                job = db.get(Job, job_id)
                job.status = "succeeded"
                job.result = result
                job.error = None
            except Deferred as exc:
                db.rollback()
                job = db.get(Job, job_id)
                job.status = "queued"
                job.attempts = max(0, job.attempts - 1)
                job.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=exc.seconds)
                job.error = f"Deferred: {exc}"
                job.payload = {**(job.payload or {}), "deferrals": int((job.payload or {}).get("deferrals", 0)) + 1}
                db.commit()
                return "deferred"
            except JobCancelled:
                db.rollback()
                job = db.get(Job, job_id)
                job.status = "cancelled"
                job.error = "Cancelled while running"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                job = db.get(Job, job_id)
                retryable = not isinstance(exc, NonRetryable) and getattr(exc, "retryable", True)
                job.error = f"{exc.__class__.__name__}: {exc}"[:2000]
                job.result = {"traceback": traceback.format_exc()[-3000:]}
                if retryable and job.attempts < job.max_attempts:
                    job.status = "retry_wait"
                    job.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds(job.attempts))
                else:
                    job.status = "failed"
                    db.add(Notification(business_id=job.business_id, kind="job_failed", severity="warning",
                                        title=f"Job failed: {job.job_type}", body=job.error[:400], link="/system"))
            job.finished_at = datetime.now(timezone.utc)
            job.heartbeat_at = job.finished_at
            db.commit()
            self.processed += 1
            return job.status
        finally:
            db.close()
            with self._lock:
                self._running.discard(job_id)

    def beat(self, db: Session) -> None:
        hb = db.get(WorkerHeartbeat, self.worker_id)
        now = datetime.now(timezone.utc)
        if hb is None:
            db.add(WorkerHeartbeat(worker_id=self.worker_id, started_at=now, last_beat_at=now, status="running"))
        else:
            hb.last_beat_at = now
            hb.jobs_processed = self.processed
            hb.status = "running"

    def tick(self, run_inline: bool = True, schedules: bool = True) -> list[str]:
        """One scheduler cycle. ``run_inline`` executes claimed jobs synchronously (tests / CLI)."""
        with self.session_factory() as db:
            self.beat(db)
            self.recover_stuck(db)
            if schedules:
                self.enqueue_due(db)
            db.commit()
            with self._lock:
                free = max(0, (self._pool._max_workers if not run_inline else 50) - len(self._running))
            claimed = self._claim(db, free) if free else []
        if run_inline:
            return [self.run_job(j) for j in claimed]
        for jid in claimed:
            self._pool.submit(self.run_job, jid)
        return []

    def drain(self, max_cycles: int = 20) -> list[str]:
        """Run ticks until no runnable jobs remain (tests/CLI)."""
        out: list[str] = []
        for _ in range(max_cycles):
            res = self.tick(run_inline=True)
            if not res:
                break
            out.extend(res)
        return out


_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler | None:
    return _scheduler


def start_scheduler() -> Scheduler:
    global _scheduler
    from . import handlers  # noqa: F401  register handlers

    _scheduler = Scheduler()
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
