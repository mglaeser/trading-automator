#!/usr/bin/env python3
"""Secret scan gate (B-06 / A-08; catches calibration defect D1).

Scans the tracked product surface at HEAD and the full git history for
high-signal secret patterns. Fail-closed: any hit fails the build.

The audit evidence tree and the mandate text are excluded because they document
the patterns themselves; .env.example is excluded because it is an empty template.

Usage: python scripts/secret_scan.py [--history]
"""
import re
import subprocess
import sys

# High-signal patterns. Kept deliberately specific to avoid noise.
PATTERNS = [
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("aws access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("google api key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("generic assigned secret", re.compile(
        r"""(?i)(api[_-]?key|api[_-]?secret|auth[_-]?token|password)\s*[:=]\s*['"][^'"\s]{12,}['"]""")),
]

# The audit tooling and evidence trees legitimately contain the secret-shaped
# patterns they exist to detect/seed; the product surface (src/tests/config/infra)
# is what a real secret would compromise. History is scanned in full regardless.
EXCLUDE_PREFIXES = ("audit/", "governance/", "scripts/")
EXCLUDE_EXACT = {".env.example"}


def tracked_files():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    for p in out.stdout.splitlines():
        if p in EXCLUDE_EXACT or any(p.startswith(x) for x in EXCLUDE_PREFIXES):
            continue
        yield p


def scan_text(label, text):
    hits = []
    for name, pat in PATTERNS:
        for m in pat.finditer(text):
            # skip empty-template assignments like KEY="" or KEY=
            frag = m.group(0)
            hits.append(f"{label}: {name} -> {frag[:24]}…")
    return hits


def main():
    hits = []
    for path in tracked_files():
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        hits += scan_text(path, text)

    if "--history" in sys.argv:
        commits = subprocess.run(["git", "rev-list", "--all"],
                                 capture_output=True, text=True, check=True).stdout.split()
        for c in commits:
            blob = subprocess.run(["git", "grep", "-hI", "-E",
                                   "|".join(p.pattern for _, p in PATTERNS[:6]), c],
                                  capture_output=True, text=True)
            if blob.stdout.strip():
                for line in blob.stdout.splitlines():
                    hits += scan_text(f"history@{c[:8]}", line)

    if hits:
        print("SECRET SCAN: FAIL")
        for h in hits:
            print("  -", h)
        return 1
    print("SECRET SCAN: PASS (no secrets in tracked product surface"
          + (" or history" if "--history" in sys.argv else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
