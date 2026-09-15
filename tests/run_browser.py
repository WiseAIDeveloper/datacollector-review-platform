"""Run existing browser scenarios against a disposable dataset and server."""

import os
import subprocess
import sys
from pathlib import Path

from tests.support import PROJECT, SOURCE, running_server


def main():
    """Run every browser scenario and report failures without touching live data."""
    failures = []
    with running_server() as client:
        environment = {
            **os.environ,
            "VIEWER_URL": client.base,
            "REVIEW_SOURCE": str(SOURCE),
            "PYTHONPATH": str(PROJECT),
        }
        for path in sorted((PROJECT / "tests/browser").glob("test_*.py")):
            result = subprocess.run(
                [sys.executable, str(path)], cwd=PROJECT, env=environment, timeout=60
            )
            if result.returncode:
                failures.append(path.name)
    if failures:
        raise SystemExit("Browser checks failed: " + ", ".join(failures))
    print("All browser scenarios passed with disposable fixtures.")


if __name__ == "__main__":
    main()
