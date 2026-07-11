"""Randomised day/night scheduler (was scheduler.py + parts of utils.py).

Each job runs at a random interval inside a [min, max] minute window. The
windows differ between day and night; day/night is derived from sunrise and
sunset at the configured location (astral). Interval windows can be adjusted
at runtime -- the engine tightens/relaxes the rebalance cadence based on
market sentiment, exactly like the old implementation.
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


class Job:
    def __init__(self, name, fn, day_interval, night_interval):
        self.name = name
        self.fn = fn
        self.intervals = {"daytime": list(day_interval), "nighttime": list(night_interval)}
        self.next_run = None

    def reschedule(self, period, now=None):
        low, high = self.intervals[period]
        delay = random.uniform(low, high) * 60.0
        self.next_run = (now or time.time()) + delay


class Scheduler:
    def __init__(self, settings):
        self._settings = settings
        self._jobs = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
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
        sched = self._settings.get("schedule", {})
        day = sched.get("daytime", {}).get(name, [30, 60])
        night = sched.get("nighttime", {}).get(name, [60, 120])
        with self._lock:
            self._jobs[name] = Job(name, fn, day, night)

    def update_interval(self, name, interval, period="both"):
        """Change a job's interval window at runtime ('day'/'night'/'both')."""
        periods = ["daytime", "nighttime"] if period == "both" else [
            "daytime" if period in ("day", "daytime") else "nighttime"
        ]
        with self._lock:
            job = self._jobs.get(name)
            if not job:
                raise KeyError(f"No job named '{name}'")
            for p in periods:
                job.intervals[p] = list(interval)
            job.reschedule(self.current_period())
        log.info("Interval for '%s' set to %s (%s)", name, interval, period)

    def run_now(self, name):
        with self._lock:
            job = self._jobs.get(name)
        if not job:
            raise KeyError(f"No job named '{name}'")
        job.fn()
        job.reschedule(self.current_period())

    def summary(self):
        period = self.current_period()
        with self._lock:
            return {
                "period": period,
                "running": self.is_running,
                "jobs": [
                    {
                        "name": job.name,
                        "interval": job.intervals[period],
                        "day_interval": job.intervals["daytime"],
                        "night_interval": job.intervals["nighttime"],
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
        if self.is_running:
            return
        self._stop.clear()
        period = self.current_period()
        with self._lock:
            for job in self._jobs.values():
                job.reschedule(period)
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="scheduler")
        self._thread.start()
        log.info("Scheduler started (period: %s)", period)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        log.info("Scheduler stopped")

    def _loop(self):
        last_period = self.current_period()
        while not self._stop.is_set():
            period = self.current_period()
            if period != last_period:
                log.info("Switched to %s schedule", period)
                with self._lock:
                    for job in self._jobs.values():
                        job.reschedule(period)
                last_period = period

            with self._lock:
                due = [j for j in self._jobs.values()
                       if j.next_run and j.next_run <= time.time()]
            for job in due:
                try:
                    log.info("Running scheduled job '%s'", job.name)
                    job.fn()
                except Exception as exc:
                    log.exception("Job '%s' failed: %s", job.name, exc)
                job.reschedule(period)

            self._stop.wait(5)
