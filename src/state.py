"""Shared runtime state observed by the web UI.

A structured, thread-safe event log plus the latest snapshot of everything
the dashboard shows.
"""

import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .exchanges.base import SwapResult

MAX_EVENTS = 300


class EngineState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self.engine_running: bool = False
        self.current_job: str | None = None
        self.last_error: str | None = None
        self.balances: list[dict[str, Any]] = []       # list of Balance.to_dict()
        self.total_value: float = 0.0
        self.loan_balance: float = 0.0
        self.market_evaluation: dict[str, Any] = {}    # last LLM market sentiment
        self.recommendations: list[dict[str, Any]] = []  # last pairwise LLM results
        self.target_distribution: list[tuple[str, float]] = []  # [(asset, pct), ...]
        self.last_refresh: float | None = None
        self.last_rebalance: float | None = None
        self.swap_history: deque[dict[str, Any]] = deque(maxlen=100)

    def log(self, message: str, level: str = "info", **details: Any) -> None:
        with self._lock:
            self._events.appendleft({
                "ts": time.time(),
                "level": level,
                "message": message,
                **({"details": details} if details else {}),
            })

    def record_swap(self, swap_result: "SwapResult") -> None:
        with self._lock:
            self.swap_history.appendleft({"ts": time.time(), **swap_result.to_dict()})

    def set(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
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
