"""Run current regression tests against a selected original Git revision."""

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def main():
    """Export original source to temporary storage and run unchanged contract tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="808746d")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.revision + "^{commit}"],
        cwd=PROJECT,
        text=True,
    ).strip()
    with tempfile.TemporaryDirectory(prefix="review-original-") as temporary:
        archive_bytes = subprocess.check_output(
            ["git", "archive", revision], cwd=PROJECT
        )
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
            archive.extractall(temporary, filter="data")
        environment = {
            **os.environ,
            "REVIEW_SOURCE": temporary,
            "PYTHONPATH": str(PROJECT),
        }
        modules = [
            "tests.test_api",
            "tests.test_storage",
            "tests.test_catalog",
            "tests.test_ingestion",
            "tests.test_edit_capture",
        ]
        command = (
            [sys.executable, "-m", "tests.run_browser"]
            if args.browser
            else [sys.executable, "-m", "unittest", *modules, "-v"]
        )
        result = subprocess.run(command, cwd=PROJECT, env=environment)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
