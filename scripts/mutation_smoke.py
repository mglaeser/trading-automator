#!/usr/bin/env python3
"""Deterministic mutation gate for the decision core (A-02 / S4; closes calibration
defect D5's class: proves the suite can detect injected faults).

Rather than a slow, non-deterministic full mutation run, this injects a fixed set
of meaningful mutations into core logic and asserts the test suite goes RED for
each. A surviving mutant (suite stays green) is a hole in the net and fails the
build. Fast, reproducible, and safe on uncommitted work (in-memory restore).

Extend MUTANTS whenever a new core invariant is added -- the corpus only grows.
"""
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_SNAP = {}


def apply(path, old, new):
    p = ROOT / path
    s = p.read_text()
    _SNAP.setdefault(path, s)
    if old not in s:
        raise SystemExit(f"mutation anchor missing in {path}: {old!r}")
    p.write_text(s.replace(old, new, 1))


def restore(path):
    if path in _SNAP:
        (ROOT / path).write_text(_SNAP.pop(path))


def suite_red():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode != 0


# (label, path, original, mutated)
MUTANTS = [
    ("round_down truncation -> rounding", "src/engine.py",
     "    return int(number * factor) / factor",
     "    return round(number * factor) / factor"),
    ("sell_buy score sign flip", "src/engine.py",
     "scores[assets[0]] = scores.get(assets[0], 0) - confidence",
     "scores[assets[0]] = scores.get(assets[0], 0) + confidence"),
    ("per-swap clamp disabled", "src/engine.py",
     "amount *= max_swap / est_value           # clamp down, never up",
     "amount *= 1.0"),
    ("daily-cap comparison flip", "src/engine.py",
     "if daily_cap > 0 and self._traded_last_24h() + est_value > daily_cap:",
     "if daily_cap > 0 and self._traded_last_24h() + est_value < daily_cap:"),
    ("sells-before-buys ordering broken", "src/engine.py",
     "for asset, diff in sorted(adjustments.items(), key=lambda kv: kv[1]):",
     "for asset, diff in sorted(adjustments.items(), key=lambda kv: kv[1], reverse=True):"),
    ("confidence clamp removed", "src/llm.py",
     "confidence = min(1.0, max(0.0, float(parsed.get(\"confidence\", 0.0))))",
     "confidence = float(parsed.get(\"confidence\", 0.0))"),
    ("action validation inverted", "src/llm.py",
     "if action not in VALID_ACTIONS:",
     "if action in VALID_ACTIONS and False:"),
    ("secret mask disabled", "src/settings.py",
     "_set_path(data, dotted, MASK)",
     "_set_path(data, dotted, current)"),
]


def main():
    killed, survived = 0, []
    print("=== mutation smoke (decision core) ===")
    for label, path, old, new in MUTANTS:
        apply(path, old, new)
        red = suite_red()
        restore(path)
        if red:
            killed += 1
            print(f"  KILLED   {label}")
        else:
            survived.append(label)
            print(f"  SURVIVED {label}  <-- suite did not catch this fault")
    score = killed / len(MUTANTS)
    print(f"=== mutation score: {killed}/{len(MUTANTS)} = {score:.2f} ===")
    if survived:
        print("Surviving mutants mean the test net has holes; add a test that kills each.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
