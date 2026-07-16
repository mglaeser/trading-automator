"""Randomised day/night scheduler.

Each job runs at a random interval inside a [min, max] minute window. Base
windows come live from settings (so UI edits apply at each job's next
scheduling), differ between day and night, and can be overridden at runtime
by the engine's market-sentiment logic to tighten or relax the cadence.

Day/night is derived from sunrise and sunset at the configured location
(astral). Start/stop is race-free: each loop owns its stop event, so a stale
thread can never be resurrected by a later start().
"""

import logging
import random
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytz
from astral import LocationInfo
from astral.sun import sun

if TYPE_CHECKING:
    from .settings import Settings

log = logging.getLogger(__name__)

FALLBACK_INTERVAL: list[float] = [30, 60]  # minutes, when settings carry no window


class Job:
    def __init__(self, name: str, fn: Callable[[], None]) -> None:
        self.name = name
        self.fn = fn
        self.override: list[float] | None = None   # [lo, hi] set by sentiment; wins over settings
        self.next_run: float | None = None


class Scheduler:
    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._stop: threading.Event | None = None   # Event owned by the running loop
        self._thread: threading.Thread | None = None

    # -- sun / period --------------------------------------------------------

    def _location(self) -> LocationInfo:
        sched = self._settings.get("schedule", {})
        return LocationInfo(
            "configured", "region",
            sched.get("timezone", "Europe/Berlin"),
            sched.get("latitude", 52.52),
            sched.get("longitude", 13.405),
        )

    def sun_times(self) -> tuple[datetime, datetime]:
        loc = self._location()
        tz = pytz.timezone(loc.timezone)
        s = sun(loc.observer, date=datetime.now(tz), tzinfo=tz)
        return s["sunrise"], s["sunset"]

    def current_period(self) -> str:
        try:
            sunrise, sunset = self.sun_times()
            now = datetime.now(sunrise.tzinfo)
            return "daytime" if sunrise < now < sunset else "nighttime"
        except Exception as exc:  # noqa: BLE001 -- bad coordinates fall back to daytime (logged)
            log.warning("Could not compute sun times: %s", exc)
            return "daytime"

    # -- jobs ------------------------------------------------------------------

    def add_job(self, name: str, fn: Callable[[], None]) -> None:
        with self._lock:
            self._jobs[name] = Job(name, fn)

    def _interval_for(self, job: Job, period: str) -> list[float]:
        if job.override:
            return job.override
        window = self._settings.get(f"schedule.{period}.{job.name}")
        if (isinstance(window, list) and len(window) == 2
                and all(isinstance(x, (int, float)) for x in window)):
            return window
        return FALLBACK_INTERVAL

    def _reschedule(self, job: Job, period: str, now: float | None = None) -> None:
        low, high = self._interval_for(job, period)
        job.next_run = (now or time.time()) + random.uniform(low, high) * 60.0

    def set_override(self, name: str, interval: Iterable[float]) -> None:
        """Sentiment-driven interval override; wins over settings until
        changed again or the process restarts."""
        with self._lock:
            job = self._jobs.get(name)
            if not job:
                raise KeyError(f"No job named '{name}'")
            if job.override != list(interval):
                job.override = list(interval)
                self._reschedule(job, self.current_period())
                log.info("Interval override for '%s': %s", name, interval)

    def summary(self) -> dict[str, Any]:
        period = self.current_period()
        with self._lock:
            return {
                "period": period,
                "running": self.is_running,
                "jobs": [
                    {
                        "name": job.name,
                        "interval": self._interval_for(job, period),
                        "override": job.override,
                        "next_run": job.next_run,
                        "minutes_until": round((job.next_run - time.time()) / 60, 1)
                        if job.next_run else None,
                    }
                    for job in self._jobs.values()
                ],
            }

    # -- loop --------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            stop = threading.Event()
            self._stop = stop
            period = self.current_period()
            for job in self._jobs.values():
                self._reschedule(job, period)
            self._thread = threading.Thread(
                target=self._loop, args=(stop,), daemon=True, name="scheduler"
            )
            self._thread.start()
        log.info("Scheduler started (period: %s)", period)

    def stop(self) -> None:
        with self._lock:
            if self._stop is not None:
                self._stop.set()
            thread, self._thread = self._thread, None
        if thread:
            thread.join(timeout=10)
        log.info("Scheduler stopped")

    def _loop(self, stop: threading.Event) -> None:
        last_period = self.current_period()
        while not stop.is_set():
            period = self.current_period()
            if period != last_period:
                log.info("Switched to %s schedule", period)
                with self._lock:
                    for job in self._jobs.values():
                        self._reschedule(job, period)
                last_period = period

            with self._lock:
                due = [j for j in self._jobs.values()
                       if j.next_run and j.next_run <= time.time()]
            for job in due:
                if stop.is_set():
                    break
                try:
                    log.info("Running scheduled job '%s'", job.name)
                    job.fn()
                except Exception as exc:
                    log.exception("Job '%s' failed: %s", job.name, exc)
                with self._lock:
                    self._reschedule(job, period)

            stop.wait(5)
