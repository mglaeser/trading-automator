#!/usr/bin/env python3
"""Dependency existence + pinning gate (B-04 / C-03; catches calibration defect D3).

For every requirement: it must be pinned with `==`, and it must actually exist on
PyPI at that version. A non-existent (slopsquat / hallucinated) or unpinned package
fails the build. Fail-closed: a network error is a failure, not a pass.

Usage: python scripts/check_deps.py [requirements.txt ...]
"""
import json
import re
import sys
import urllib.request

REQ_FILES = sys.argv[1:] or ["requirements.txt"]
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s#]+)")


def pypi(name):
    url = f"https://pypi.org/pypi/{name}/json"
    with urllib.request.urlopen(url, timeout=20) as r:  # noqa: S310 -- fixed https host
        return json.load(r)


def main():
    problems, checked = [], 0
    for reqfile in REQ_FILES:
        try:
            lines = open(reqfile).read().splitlines()
        except OSError as exc:
            problems.append(f"{reqfile}: cannot read ({exc})")
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = PIN.match(line)
            if not m:
                problems.append(f"{reqfile}: '{line}' is not pinned with == (unpinned dependency)")
                continue
            name, version = m.group(1), m.group(2)
            checked += 1
            try:
                data = pypi(name)
            except Exception as exc:  # noqa: BLE001 -- fail closed on any resolution failure
                problems.append(f"{name}: does not resolve on PyPI ({type(exc).__name__}) "
                                f"-- non-existent or unreachable")
                continue
            releases = data.get("releases", {})
            if version not in releases:
                problems.append(f"{name}=={version}: version not found on PyPI "
                                f"(latest known: {data.get('info', {}).get('version')})")

    if problems:
        print("DEPENDENCY GATE: FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print(f"DEPENDENCY GATE: PASS ({checked} pinned packages exist on PyPI)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
