#!/usr/bin/env python3
"""Model-pin lint (B-13): forbid floating model aliases in production config.

A model id ending in `-latest`, or the bare word `latest`, resolves to whatever
the provider currently serves -- so behaviour changes while the code does not.
This gate fails on such aliases in src/settings.py defaults and in any committed
config. Dated/immutable snapshot ids pass.

It does NOT (and cannot) prove a given id is a snapshot; it catches the known
floating forms and leaves a documented recommendation to pin to a dated snapshot.
"""
import pathlib
import re
import sys

FLOATING = re.compile(r'["\']([a-z0-9.\-]*(?:-latest|:latest))["\']', re.IGNORECASE)
BARE_LATEST = re.compile(r'model["\']?\s*[:=]\s*["\']latest["\']', re.IGNORECASE)

TARGETS = ["src/settings.py"]
# include a committed config if present
if pathlib.Path("config/config.json").exists():
    TARGETS.append("config/config.json")


def main():
    problems = []
    for path in TARGETS:
        p = pathlib.Path(path)
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if "model" not in line.lower():
                continue
            for m in FLOATING.finditer(line):
                problems.append(f"{path}:{i}: floating model alias '{m.group(1)}' "
                                f"-- pin to a dated snapshot")
            if BARE_LATEST.search(line):
                problems.append(f"{path}:{i}: bare 'latest' model -- pin to a dated snapshot")
    if problems:
        print("MODEL-PIN GATE: FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print("MODEL-PIN GATE: PASS (no floating '-latest' model aliases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
