"""Randomised day/night scheduler (was scheduler.py + parts of utils.py).

Each job runs at a random interval inside a [min, max] minute window. Base
windows come live from settings (so UI edits apply at each job's next
scheduling), differ between day and night, and can be overridden at runtime
by the engine's market-sentiment logic -- exactly like the old
implementation tightened/relaxed the cadence.

Day/night is derived from sunrise and sunset at the configured location
(astral). Start/stop is race-free: each loop owns its stop event, so a stale
thread can never be resurrected by a later start().
"""

import logging
import random
import threading
import time
from datetime import datetime

import pytz
from astral import LocationInfo
from astral.sun import sun

log = logging.getLogger(__name__)

FALLBACK_INTERVAL = [30, 60]  # minutes, when settings carry no window


class Job:
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn
        self.override = None   # [lo, hi] set by sentiment; wins over settings
        self.next_run = None


class Scheduler:
    def __init__(self, settings):
        self._settings = settings
        self._jobs = {}
        self._lock = threading.RLock()
        self._stop = None      # Event owned by the currently running loop
        self._thread = None

    # -- sun / period --------------------------------------------------------

    def _location(self):
        sched = self._settings.get("schedule", {})
        return LocationInfo(
            "configured", "region",
            sched.get("timezone", "Europe/Berlin"),
            sched.get("latitude", 52.52),
            sched.get("longitude", 13.405),
        )

    def sun_times(self):
        loc = self._location()
        tz = pytz.timezone(loc.timezone)
        s = sun(loc.observer, date=datetime.now(tz), tzinfo=tz)
        return s["sunrise"], s["sunset"]

    def current_period(self):
        try:
            sunrise, sunset = self.sun_times()
            now = datetime.now(sunrise.tzinfo)
            return "daytime" if sunrise < now < sunset else "nighttime"
        except Exception as exc:  # bad coordinates etc. -- default to daytime
            log.warning("Could not compute sun times: %s", exc)
            return "daytime"

    # -- jobs ------------------------------------------------------------------

    def add_job(self, name, fn):
        with self._lock:
            self._jobs[name] = Job(name, fn)

    def _interval_for(self, job, period):
        if job.override:
            return job.override
        window = self._settings.get(f"schedule.{period}.{job.name}")
        if (isinstance(window, list) and len(window) == 2
                and all(isinstance(x, (int, float)) for x in window)):
            return window
        return FALLBACK_INTERVAL

    def _reschedule(self, job, period, now=None):
        low, high = self._interval_for(job, period)
        job.next_run = (now or time.time()) + random.uniform(low, high) * 60.0

    def set_override(self, name, interval):
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

    def summary(self):
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
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
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

    def stop(self):
        with self._lock:
            if self._stop is not None:
                self._stop.set()
            thread, self._thread = self._thread, None
        if thread:
            thread.join(timeout=10)
        log.info("Scheduler stopped")

    def _loop(self, stop):
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
