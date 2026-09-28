"""Check the name normalization script on disposable datasets only."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import INDEXES, PROJECT, SOURCE, dataset, write_csv

if not (SOURCE / "scripts/normalize_names.py").is_file():
    raise unittest.SkipTest("Normalization script is not part of this source revision")

NAMING = {
    "lighting": {
        "column": "lighting",
        "accepted": ["office_white", "office_dark", "office_yellow"],
    },
    "identity": {"column": "subject", "accepted": []},
    "device": {
        "app": {"column": "capture_device", "fallback": "input_sensor.model"},
        "web": {"column": "capture_device"},
        "accepted": {
            "iphone_13": {"capture_device": ["iphone-13"]},
            "galaxy": {"input_sensor.model": ["SM-1"]},
        },
    },
}


class NormalizeNamesTests(unittest.TestCase):
    """Dry runs change nothing; applying converts values and keeps backups."""

    def setUp(self):
        """Create captures, annotations, and a project plan with old names."""
        temporary = tempfile.TemporaryDirectory(prefix="normalize-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.rows = dataset(self.data, count=3)
        self.rows[1]["lighting"] = "white"
        self.rows[2]["lighting"] = "strange"
        # A quoted cell proves unchanged rows keep their exact bytes.
        self.rows[2]["user"] = "a, b"
        write_csv(self.data / "genuine" / INDEXES[0], self.rows)
        self.annotation = (
            self.data / "genuine/mykadfront/datacollector_annotation/capture-0.json"
        )
        self.annotation.write_text(
            '{\n  "lighting": "dark",\n  "capture_device": "iphone-13",\n  "uuid": "capture-0"\n}'
        )
        project = self.root / "projects/p1"
        project.mkdir(parents=True)
        write_csv(
            project / "plan.csv",
            [dict(folder="genuine", lighting="dark", sdk="app", device="SM-1")],
        )
        write_csv(
            project / "plan_batches.csv",
            [dict(batch_name="genuine", expected_lighting="dark;white")],
        )
        (self.root / "naming.json").write_text(json.dumps(NAMING))

    def run_script(self, *extra):
        """Run the script and return its exit code and JSON report."""
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT / "scripts/normalize_names.py"),
                "--dataset",
                str(self.data),
                "--projects-root",
                str(self.root / "projects"),
                "--naming",
                str(self.root / "naming.json"),
                "--lighting",
                "dark=office_dark",
                "--lighting",
                "white=office_white",
                *extra,
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode, json.loads(result.stdout)

    def snapshot(self):
        """Read every file under the fixture directories."""
        return {
            p: p.read_bytes()
            for base in (self.data, self.root / "projects")
            for p in base.rglob("*")
            if p.is_file()
        }

    def test_dry_run_reports_without_writing(self):
        """A dry run lists changes and unknown values and writes nothing."""
        before = self.snapshot()
        code, report = self.run_script()
        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(report["mode"], "dry run")
        changed = {
            (c["field"], c["old"], c["new"]): c["count"] for c in report["changes"]
        }
        self.assertEqual(changed[("lighting", "dark", "office_dark")], 4)
        self.assertEqual(changed[("lighting", "white", "office_white")], 2)
        self.assertEqual(changed[("device", "iphone-13", "iphone_13")], 4)
        self.assertEqual(changed[("device", "SM-1", "galaxy")], 1)
        # Unlisted values are reported, never guessed: the fixture's other
        # annotations still say office-white.
        self.assertEqual(
            report["unmapped"],
            [
                dict(field="lighting", value="office-white", count=2),
                dict(field="lighting", value="strange", count=1),
            ],
        )

    def test_apply_converts_values_and_keeps_backups(self):
        """Applying rewrites only mapped cells and backs up the originals."""
        index = self.data / "genuine" / INDEXES[0]
        original = index.read_bytes()
        backup = self.root / "backup"
        code, report = self.run_script("--apply", "--backup", str(backup))
        self.assertEqual(code, 0)
        self.assertEqual(report["files_changed"], 4)
        lines = index.read_text().splitlines()
        self.assertIn(",office_dark,iphone_13,", lines[1])
        self.assertIn(",office_white,iphone_13,", lines[2])
        self.assertIn(",strange,iphone_13,", lines[3])
        self.assertIn('"a, b"', lines[3])
        self.assertEqual((backup / "data/genuine" / INDEXES[0]).read_bytes(), original)
        annotation = self.annotation.read_text()
        self.assertEqual(
            annotation,
            '{\n  "lighting": "office_dark",\n  "capture_device": "iphone_13",\n  "uuid": "capture-0"\n}',
        )
        plan = (self.root / "projects/p1/plan.csv").read_text()
        self.assertIn("genuine,office_dark,app,galaxy", plan)
        batches = (self.root / "projects/p1/plan_batches.csv").read_text()
        self.assertIn("office_dark;office_white", batches)
        self.assertEqual(self.run_script()[1]["files_changed"], 0)

    def test_apply_requires_new_backup_directory(self):
        """Applying without a fresh backup directory is refused."""
        (self.root / "backup").mkdir()
        before = self.snapshot()
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT / "scripts/normalize_names.py"),
                "--dataset",
                str(self.data),
                "--naming",
                str(self.root / "naming.json"),
                "--apply",
                "--backup",
                str(self.root / "backup"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
