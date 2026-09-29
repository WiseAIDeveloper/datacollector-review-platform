"""Check the field rename script on disposable datasets only."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import INDEXES, PROJECT, dataset, write_csv


class RenameFieldsTests(unittest.TestCase):
    """Dry runs change nothing; applying renames every stored copy with backups."""

    def setUp(self):
        """Create captures, a plan, and an older ingestion history using old names."""
        temporary = tempfile.TemporaryDirectory(prefix="rename-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        rows = [
            {
                ("lighting" if k == "capture_env_lighting" else k): v
                for k, v in r.items()
            }
            for r in dataset(self.data, count=2)
        ]
        rows[1]["user"] = "a, b"
        write_csv(self.data / "genuine" / INDEXES[0], rows)
        self.annotation = (
            self.data / "genuine/mykadfront/datacollector_annotation/capture-0.json"
        )
        self.annotation.write_text('{\n  "lighting": "dark",\n  "uuid": "capture-0"\n}')
        self.project = self.root / "projects/p1"
        self.project.mkdir(parents=True)
        write_csv(
            self.project / "plan.csv",
            [dict(folder="genuine", lighting="dark", sdk="web", device="phone")],
        )
        write_csv(
            self.project / "plan_batches.csv",
            [
                dict(
                    batch_name="genuine",
                    expected_web_devices="phone;tablet",
                    expected_lighting="dark",
                    expected_app_devices="tablet;watch",
                )
            ],
        )
        with sqlite3.connect(self.project / "ingestion.sqlite") as db:
            db.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY, key TEXT UNIQUE, status TEXT, detected_at TEXT, batch TEXT, filename TEXT, uuid TEXT, lighting TEXT, subject TEXT, sdk TEXT, device TEXT, test_plan TEXT, creation_time TEXT)"
            )
            db.execute(
                "CREATE TABLE actions (id INTEGER PRIMARY KEY, action TEXT, occurred_at TEXT, batch TEXT, uuid TEXT, filename TEXT, changes TEXT)"
            )
            db.execute(
                "INSERT INTO events (key, lighting, subject, device) "
                "VALUES ('genuine/capture-0/capture-0.jpg', 'dark', 'fixture', 'phone')"
            )
            db.execute(
                "INSERT INTO actions (action, changes) VALUES ('modified', ?)",
                (json.dumps({"lighting": {"from": "dark", "to": "office-white"}}),),
            )

    def run_script(self, *extra):
        """Run the script and return its exit code and JSON report."""
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT / "scripts/rename_fields.py"),
                "--dataset",
                str(self.data),
                "--projects-root",
                str(self.root / "projects"),
                "--rename",
                "lighting=capture_env_lighting",
                "--rename",
                "device=capture_device",
                "--rename",
                "expected_lighting=expected_capture_env_lighting",
                "--merge",
                "expected_web_devices,expected_app_devices=expected_capture_device",
                *extra,
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode, json.loads(result.stdout)

    def snapshot(self):
        """Read every file under the fixture directories."""
        return {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_dry_run_reports_without_writing(self):
        """A dry run counts files and writes nothing."""
        before = self.snapshot()
        code, report = self.run_script()
        self.assertEqual((code, report["mode"]), (0, "dry run"))
        self.assertEqual(report["files_changed"], 5)
        self.assertEqual(self.snapshot(), before)

    def test_apply_renames_everywhere_and_keeps_backups(self):
        """Headers, keys, plan lists, and history all use the new names."""
        index = self.data / "genuine" / INDEXES[0]
        original = index.read_text()
        code, report = self.run_script("--apply", "--backup", str(self.root / "b"))
        self.assertEqual(code, 0, report)
        lines = index.read_text().splitlines()
        self.assertIn("capture_env_lighting", lines[0].split(","))
        self.assertEqual(lines[1:], original.splitlines()[1:])
        self.assertEqual(
            (self.root / "b/data/genuine" / INDEXES[0]).read_text(), original
        )
        self.assertEqual(
            self.annotation.read_text(),
            '{\n  "capture_env_lighting": "dark",\n  "uuid": "capture-0"\n}',
        )
        self.assertEqual(
            (self.project / "plan.csv").read_text().splitlines()[0],
            "folder,capture_env_lighting,sdk,capture_device",
        )
        batches = (self.project / "plan_batches.csv").read_text().splitlines()
        self.assertEqual(
            batches,
            [
                "batch_name,expected_capture_device,expected_capture_env_lighting",
                "genuine,phone;tablet;watch,dark",
            ],
        )
        log = json.loads((self.project / "ingestion.jsonl").read_text())
        self.assertEqual(
            (log["capture_env_lighting"], log["capture_device"], log["subject"]),
            ("dark", "phone", "fixture"),
        )
        action = json.loads((self.project / "actions.jsonl").read_text())
        self.assertEqual(list(action["changes"]), ["capture_env_lighting"])
        self.assertEqual(self.run_script()[1]["files_changed"], 0)


if __name__ == "__main__":
    unittest.main()
