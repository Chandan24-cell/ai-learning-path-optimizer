from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HISTORY_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "bcrypt hash": re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}"),
    "common API key": re.compile(r"\b(?:sk_live_|sk-proj-|gh[pousr]_|glpat-)[A-Za-z0-9_-]{16,}\b"),
}


def _run(name: str, args: list[str]) -> None:
    local_tool = ROOT / ".venv" / "bin" / args[0]
    executable = shutil.which(args[0]) or (str(local_tool) if local_tool.is_file() else None)
    if not executable:
        print(f"{name}: NOT RUN (tool not installed)")
        return
    command = [executable, *args[1:]]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    print(f"--- {name}: exit {result.returncode} ---")
    print(result.stdout.strip() or "(no standard output)")
    if result.stderr.strip():
        print("STDERR:")
        print(result.stderr.strip())


def _history_scan() -> None:
    result = subprocess.run(
        [
            "git",
            "log",
            "--all",
            "-p",
            "--no-ext-diff",
            "--",
            ".",
            ":!outputs",
            ":!*.png",
            ":!*.keras",
            ":!*.npz",
            ":!*.joblib",
            ":!*.pkl",
            ":!*.db",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    findings = []
    for label, pattern in HISTORY_PATTERNS.items():
        matches = pattern.findall(result.stdout)
        if matches:
            findings.append(f"{label}: {len(matches)} matching occurrence(s)")
    print("--- Git history secret-pattern scan ---")
    print("\n".join(findings) if findings else "No matches in scanned text diffs.")
    print("Note: This bounded pattern scan is not a substitute for a dedicated secret scanner.")


def main() -> None:
    _run(
        "pip-audit",
        [
            "pip-audit",
            "-r",
            str(ROOT / "requirements.txt"),
            "-r",
            str(ROOT / "requirements-dev.txt"),
        ],
    )
    _run(
        "Bandit",
        [
            "bandit",
            "-r",
            str(ROOT / "app"),
            str(ROOT / "src"),
        ],
    )
    _history_scan()


if __name__ == "__main__":
    main()
