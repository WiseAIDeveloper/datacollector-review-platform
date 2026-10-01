from tests import support  # Select the requested original or current source.
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

IngestionLog = support.load_application("ingestion").IngestionLog


class IngestionTests(unittest.TestCase):
    def setUp(self):
        """Create disposable fixtures for this test."""
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = IngestionLog(
            self.root, self.root / "history.sqlite", support.fixture_naming()
        )

    def tearDown(self):
        """Close fixture resources and remove temporary files."""
        self.log.db.close()
        self.tmp.cleanup()

    def write_batch(self, names, batch="genuine", images=True):
        """Create annotation rows and optional images for scanner tests."""
        folder = self.root / batch
        folder.mkdir(exist_ok=True)
        rows = [
            dict(
                uuid=n,
                filename=n + ".jpg",
                ori_path="orig/" + n + ".jpg",
                capture_env_lighting="dark",
                subject="fixture",
                capture_device="iphone-13",
                input_sensor="websdk;mobilesafari;ios;mobile",
                test_plan_name="colour_print_enhancement_2",
            )
            for n in names
        ]
        support.write_csv(folder / "index_annotation_.csv", rows)
        if images:
            (folder / "orig").mkdir(exist_ok=True)
            for n in names:
                (folder / "orig" / (n + ".jpg")).write_bytes(b"image")
        return folder

    def test_baseline_new_and_no_repeat(self):
        """Verify baseline new and no repeat."""
        self.write_batch(["old"])
        self.log.scan()
        self.assertEqual(self.log.snapshot()["existing"], 1)
        self.write_batch(["old", "new"])
        self.log.scan()
        self.log.scan()
        state = self.log.snapshot()
        self.assertEqual((state["total"], state["ingested"]), (2, 1))
        event = state["events"][0]
        self.assertEqual(
            (
                event["filename"],
                event["fields"]["capture_env_lighting"],
                event["sdk"],
                event["fields"]["capture_device"],
            ),
            ("new.jpg", "dark", "web", "iphone-13"),
        )

    def test_known_captures_skip_normalization_but_check_images(self):
        """Repeated scans preserve immutable history and still count missing images."""
        folder = self.write_batch(["old"])
        self.log.scan()
        with patch.object(
            support.load_application("ingestion"),
            "logged_fields",
            side_effect=AssertionError("reprocessed known capture"),
        ):
            self.log.scan()
            (folder / "orig/old.jpg").unlink()
            self.log.scan()
        self.assertEqual(self.log.snapshot()["total"], 1)
        self.assertEqual(self.log.status["pending_images"], 1)
        self.write_batch(["old", "new"])
        self.log.scan()
        self.assertEqual(self.log.snapshot()["ingested"], 1)

    def test_restart_and_deleted_history(self):
        """Verify restart and deleted history."""
        folder = self.write_batch(["old"])
        self.log.scan()
        self.log.db.close()
        self.log = IngestionLog(
            self.root, self.root / "history.sqlite", support.fixture_naming()
        )
        self.log.scan()
        (folder / "orig/old.jpg").unlink()
        self.log.scan()
        self.assertEqual(self.log.snapshot()["total"], 1)
        self.write_batch(["old", "new"])
        self.log.scan()
        self.assertEqual(self.log.snapshot()["ingested"], 1)

    def test_wait_for_image_and_exclusions(self):
        """Verify wait for image and exclusions."""
        self.log.scan()
        self.write_batch(["late"], images=False)
        for batch in ["test", "webcam_genuine", "webcam_replay"]:
            self.write_batch(["excluded"], batch)
        self.log.scan()
        self.assertEqual(self.log.snapshot()["total"], 0)
        self.assertEqual(self.log.snapshot()["pending_images"], 1)
        self.write_batch(["late"])
        self.log.scan()
        self.assertEqual(self.log.snapshot()["ingested"], 1)

    def test_duplicate_rows_and_pagination(self):
        """Verify duplicate rows and pagination."""
        self.write_batch(["one", "one", "two", "three"])
        self.log.scan()
        first = self.log.snapshot(2)
        second = self.log.snapshot(2, first["next_before"])
        self.assertEqual(first["total"], 3)
        self.assertEqual(len(second["events"]), 1)
        self.assertFalse(
            {r["id"] for r in first["events"]} & {r["id"] for r in second["events"]}
        )

    def test_malformed_csv_retries(self):
        """Verify malformed csv retries."""
        folder = self.write_batch(["one"])
        (folder / "index_annotation_.csv").write_text("uuid,filename,ori_path\none\n")
        self.log.scan()
        self.assertTrue(self.log.snapshot()["errors"])
        self.assertEqual(self.log.snapshot()["total"], 0)
        self.write_batch(["one"])
        self.log.scan()
        self.assertFalse(self.log.snapshot()["errors"])

    def test_physical_log_and_rebuild(self):
        """Verify physical log and rebuild."""
        import json

        self.write_batch(["one"])
        self.log.scan()
        self.write_batch(["one", "two"])
        self.log.scan()
        self.log.scan()
        path = self.root / "history.jsonl"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([r["filename"] for r in lines], ["one.jpg", "two.jpg"])
        self.assertEqual([r["status"] for r in lines], ["existing", "ingested"])
        self.assertEqual(lines[1]["capture_env_lighting"], "dark")
        self.assertEqual(lines[1]["capture_device"], "iphone-13")
        self.assertNotIn("fields", lines[1])
        path.unlink()
        self.log.scan()
        self.assertEqual(len(path.read_text().splitlines()), 2)

    def test_current_metadata_overlay_preserves_history(self):
        """Verify current metadata overlay preserves history."""
        with_current_metadata = support.load_application(
            "ingestion"
        ).with_current_metadata

        self.write_batch(["one"])
        self.log.scan()
        snapshot = self.log.snapshot()
        before = self.log.log_path.read_bytes()
        original = snapshot["events"][0]
        live = dict(
            key=original["key"],
            folder="genuine",
            sdk="app",
            fields=dict(capture_env_lighting="office-yellow", subject="corrected"),
            naming={},
            metadata=dict(uuid="one", filename="one.jpg", test_plan_name="plan"),
        )
        result = with_current_metadata(snapshot, [live])
        event = result["events"][0]
        self.assertEqual(
            (event["fields"], event["sdk"], event["test_plan"]),
            (live["fields"], "app", "plan"),
        )
        self.assertEqual(
            snapshot["events"][0]["fields"]["capture_env_lighting"], "dark"
        )
        self.assertEqual(self.log.log_path.read_bytes(), before)
        self.assertFalse(with_current_metadata(snapshot, [])["events"][0]["available"])

    def test_older_columns_move_into_fields(self):
        """An older database keeps each per-field column under its own name."""
        import sqlite3

        self.log.db.close()
        path = self.root / "old.sqlite"
        db = sqlite3.connect(path)
        db.execute(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, key TEXT UNIQUE, status TEXT, detected_at TEXT, batch TEXT, filename TEXT, uuid TEXT, lighting TEXT, subject TEXT, sdk TEXT, device TEXT, test_plan TEXT, creation_time TEXT)"
        )
        db.execute(
            "INSERT INTO events (key, status, lighting, subject, sdk, device) "
            "VALUES ('a/b/c', 'existing', 'dark', 'fixture', 'web', 'iphone-13')"
        )
        db.commit()
        db.close()
        self.log = IngestionLog(self.root, path, support.fixture_naming())
        event = self.log.snapshot()["events"][0]
        self.assertEqual(
            (event["key"], event["sdk"], event["fields"]),
            (
                "a/b/c",
                "web",
                dict(lighting="dark", subject="fixture", device="iphone-13"),
            ),
        )

    def test_action_history_and_physical_file(self):
        """Verify action history and physical file."""
        import json

        self.log.record_action(
            "modified",
            "genuine",
            "one",
            "one.jpg",
            {"lighting": {"from": "dark", "to": "office-white"}},
        )
        self.log.record_action("deleted", "genuine", "two", "two.jpg")
        actions = self.log.snapshot()["actions"]
        self.assertEqual([a["action"] for a in actions], ["deleted", "modified"])
        lines = [
            json.loads(line)
            for line in (self.root / "actions.jsonl").read_text().splitlines()
        ]
        self.assertEqual(lines[0]["changes"]["lighting"]["to"], "office-white")
        self.log.db.close()
        self.log = IngestionLog(
            self.root, self.root / "history.sqlite", support.fixture_naming()
        )
        self.assertEqual(self.log.snapshot()["action_total"], 2)

    def test_app_sensor(self):
        """App captures log the detected model as their device."""
        logged_fields = support.load_application("ingestion").logged_fields
        naming = support.fixture_naming()()
        for sensor, model in [
            ("{'model':'JNY-LX2'}", "JNY-LX2"),
            ("model:iPhone14,ios:26.2", "iPhone14"),
        ]:
            sdk, fields = logged_fields(naming, {"input_sensor": sensor})
            self.assertEqual((sdk, fields["capture_device"]), ("app", model))

    def test_scanner_loop(self):
        """Verify scanner loop."""
        calls = []

        def scan():
            """Record one scanner iteration and stop the fixture worker."""
            calls.append(1)
            self.log.stop.set()

        self.log.scan = scan
        self.log.run()
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
