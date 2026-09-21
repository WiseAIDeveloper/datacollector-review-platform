"""Verify folder discovery and project-local history with disposable captures."""

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.ingestion import IngestionLog
from tests.support import running_server
from tests.test_projects import project_payload


def add_folder(client, identifier, other=False):
    """Add an unregistered project by copying only its two plan files."""
    folder = client.root / "project-folders" / identifier
    folder.mkdir(parents=True)
    payload = project_payload(client, plan="other" if other else None)
    (folder / "plan.csv").write_text(payload["matrix_csv"])
    (folder / "plan_batches.csv").write_text(payload["batches_csv"])
    return folder


class FolderProjectTests(unittest.TestCase):
    """Exercise live discovery and isolation without altering the original app."""

    def test_discovery_selection_and_upload(self):
        """Discover external folders, scope captures, and create folders through uploads."""
        with running_server(folder_mode=True) as client:
            self.assertEqual(client.request("/api/projects")[1], [])
            self.assertIn(b"Select a project", client.request("/")[1])
            self.assertEqual(client.request("/api/captures")[0], 400)
            add_folder(client, "001_First")
            second = add_folder(client, "002_Second", other=True)
            self.assertEqual(
                [r["id"] for r in client.request("/api/projects")[1]],
                ["001_First", "002_Second"],
            )
            for identifier, count in (("001_First", 5), ("002_Second", 0)):
                self.assertEqual(
                    len(client.request("/api/captures?project=" + identifier)[1]), count
                )
            status, uploaded, _ = client.request(
                "/api/projects", project_payload(client, "Uploaded")
            )
            self.assertEqual(status, 200)
            self.assertTrue(
                (
                    client.root / "project-folders" / uploaded["id"] / "project.json"
                ).exists()
            )
            self.assertEqual(len(client.request("/api/projects")[1]), 3)
            (second / "plan.csv").unlink()
            self.assertIn("error", client.request("/api/projects")[1][1])
            self.assertEqual(client.request("/api/matrix?project=002_Second")[0], 400)
            self.assertEqual(client.request("/api/project?project=..%2Fother")[0], 400)

    def test_logs_restore_and_isolation(self):
        """Restore copied logs once and keep project history and quality decisions separate."""
        with running_server() as source, running_server(folder_mode=True) as client:
            source.request(
                "/api/edit-capture",
                dict(
                    folder="genuine",
                    uuid="capture-0",
                    filename="capture-0.jpg",
                    expected=source.rows[0],
                    changes={"subject": "updated"},
                ),
            )
            first = add_folder(client, "001_First")
            second = add_folder(client, "002_Second", other=True)
            for filename in ("ingestion.jsonl", "actions.jsonl"):
                shutil.copy2(source.root / filename, first / filename)
            history = client.request("/api/ingestion?project=001_First")[1]
            self.assertEqual(history["total"], 5)
            self.assertEqual(history["action_total"], 1)
            self.assertEqual(
                history["actions"][0]["changes"]["subject"]["to"], "updated"
            )
            self.assertEqual(
                client.request("/api/ingestion?project=002_Second")[1]["action_total"],
                0,
            )
            self.assertEqual(
                client.request(
                    "/api/quality?project=001_First",
                    {
                        "key": "genuine/capture-0/capture-0.jpg",
                        "status": "pass",
                        "expected": None,
                    },
                )[0],
                200,
            )
            self.assertTrue((first / "quality_reviews.json").is_file())
            self.assertFalse((second / "quality_reviews.json").exists())
            client.restart()
            self.assertEqual(
                client.request("/api/ingestion?project=001_First")[1]["action_total"], 1
            )
            self.assertEqual(client.request("/api/quality?project=002_Second")[1], {})

    def test_bad_log_import_rolls_back(self):
        """Malformed copied history cannot be replaced by an empty scanner export."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "ingestion.jsonl"
            log.write_text('{"broken": true}\n')
            ingestion = IngestionLog(root, root / "state.sqlite", log_path=log)
            try:
                with self.assertRaises(ValueError):
                    ingestion.restore_logs()
                self.assertEqual(
                    ingestion.db.execute("SELECT count(*) FROM events").fetchone()[0], 0
                )
                self.assertEqual(log.read_text(), '{"broken": true}\n')
            finally:
                ingestion.close()
