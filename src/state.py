"""Shared runtime state observed by the web UI.

Replaces the old screenshots/log-tail workflow with a structured, thread-safe
event log plus the latest snapshot of everything the dashboard shows.
"""

import threading
import time
from collections import deque

MAX_EVENTS = 300


class EngineState:
    def __init__(self):
        self._lock = threading.RLock()
        self._events = deque(maxlen=MAX_EVENTS)
        self.engine_running = False
        self.current_job = None
        self.last_error = None
        self.balances = []            # list of Balance.to_dict()
        self.total_value = 0.0
        self.loan_balance = 0.0
        self.market_evaluation = {}   # last LLM market sentiment
        self.recommendations = []     # last pairwise LLM results
        self.target_distribution = [] # [(asset, pct), ...]
        self.last_refresh = None
        self.last_rebalance = None
        self.swap_history = deque(maxlen=100)

    def log(self, message, level="info", **details):
        with self._lock:
            self._events.appendleft({
                "ts": time.time(),
                "level": level,
                "message": message,
                **({"details": details} if details else {}),
            })

    def record_swap(self, swap_result):
        with self._lock:
            self.swap_history.appendleft({"ts": time.time(), **swap_result.to_dict()})

    def set(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def to_dict(self):
        with self._lock:
            return {
                "engine_running": self.engine_running,
                "current_job": self.current_job,
                "last_error": self.last_error,
                "balances": list(self.balances),
                "total_value": round(self.total_value, 2),
                "loan_balance": round(self.loan_balance, 2),
                "market_evaluation": dict(self.market_evaluation),
                "recommendations": list(self.recommendations),
                "target_distribution": list(self.target_distribution),
                "last_refresh": self.last_refresh,
                "last_rebalance": self.last_rebalance,
                "swap_history": list(self.swap_history),
                "events": list(self._events),
            }
