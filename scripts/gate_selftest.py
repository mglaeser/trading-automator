#!/usr/bin/env python3
"""Calibration heartbeat (A-36 / S12): re-run the seeded-defect corpus against the
INSTALLED gates and assert each is still caught. A gate that stops catching its
seed is a failed gate and fails the build.

Runs on a scratch copy via git: each defect is applied, the responsible gate is
run and must FAIL (exit != 0 == caught), then reverted. Never mutates committed
state. D5 (weak-suite class) is covered by the weekly mutation gate, not this fast
lane; it is reported as deferred, not skipped silently.
"""
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


_SNAPSHOTS = {}


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def revert(path):
    """Restore from the in-memory snapshot taken by apply() -- safe on
    uncommitted work (does not depend on git HEAD)."""
    if path in _SNAPSHOTS:
        (ROOT / path).write_text(_SNAPSHOTS.pop(path))


def apply(path, old, new):
    p = ROOT / path
    s = p.read_text()
    _SNAPSHOTS.setdefault(path, s)
    assert old in s, f"anchor missing in {path}"
    p.write_text(s.replace(old, new, 1))


def gate_caught(cmd):
    """A gate 'catches' when it exits non-zero on the defect."""
    return sh(cmd).returncode != 0


DEFECTS = [
    # (name, apply_fn, gate_cmd, revert_path)
    ("D1 hard-coded credential",
     lambda: apply("src/llm.py",
                   'SYSTEM_PROMPT = "You are a crypto finance expert responding in JSON."',
                   'SYSTEM_PROMPT = "x"\n_K = "sk-ant-api03-'+'A'*50+'"'),
     [sys.executable, "scripts/secret_scan.py"], "src/llm.py"),
    ("D2 removed universe guard",
     lambda: apply("src/engine.py",
                   'if spec is None or not spec.get("crypto", True):\n'
                   '                continue  # unconfigured assets and stables stay',
                   'if spec is None:\n                pass'),
     [sys.executable, "-m", "pytest", "-q", "tests/test_engine.py::test_sell_all_only_configured_crypto"],
     "src/engine.py"),
    ("D3 non-existent dependency",
     lambda: apply("requirements.txt", "python-dotenv==1.2.2",
                   "python-dotenv==1.2.2\ntradingview-ta-helper==0.4.2"),
     [sys.executable, "scripts/check_deps.py"], "requirements.txt"),
    ("D4 swallowed exception",
     lambda: apply("src/engine.py",
                   "        result = client.swap(from_asset, to_asset, amount)\n"
                   "        self._trade_window.append",
                   "        try:\n            result = client.swap(from_asset, to_asset, amount)\n"
                   "        except Exception:\n            return None\n"
                   "        self._trade_window.append"),
     [sys.executable, "-m", "ruff", "check", "src/engine.py"], "src/engine.py"),
    ("D6 unvalidated model output -> action",
     lambda: apply("src/llm.py",
                   'if action not in VALID_ACTIONS:\n'
                   '                raise ValueError(f"invalid action {action!r}")',
                   'if False:\n                raise ValueError("x")'),
     [sys.executable, "-m", "pytest", "-q",
      "tests/test_llm_and_exchange.py::test_swap_evaluation_rejects_bad_action"], "src/llm.py"),
]


def main():
    caught = 0
    print("=== gate self-test (calibration heartbeat) ===")
    for name, ap, gate, path in DEFECTS:
        try:
            ap()
            ok = gate_caught(gate)
        finally:
            revert(path)
        print(f"  {'CAUGHT' if ok else 'ESCAPED'}  {name}  via {' '.join(gate[-2:])}")
        caught += ok
    total = len(DEFECTS)
    print(f"=== fast-lane catch rate: {caught}/{total} "
          f"(D5 weak-suite class -> weekly mutation gate) ===")
    if caught < total:
        print("A gate stopped catching its seeded defect -- FAILED CALIBRATION.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
