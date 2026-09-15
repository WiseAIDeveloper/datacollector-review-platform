"""Characterize the original capture storage and ingestion functions."""

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import INDEXES, dataset
import delete_capture
import edit_capture
import ingestion
import quality_reviews


class StorageTests(unittest.TestCase):
    """Exercise changes and failure paths only on synthetic files."""

    def setUp(self):
        """Create two captures and register automatic fixture cleanup."""
        temporary = tempfile.TemporaryDirectory(prefix="storage-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rows = dataset(self.root, count=2)
        self.row = self.rows[0]
        self.folder = self.root / "genuine"

    def edit(self, changes, expected=None):
        """Edit the first capture with its original optimistic-lock snapshot."""
        return edit_capture.edit_capture(
            self.root,
            "genuine",
            self.row["uuid"],
            self.row["filename"],
            changes,
            self.row if expected is None else expected,
        )

    def test_remove_row_preserves_bom_multiline_and_other_bytes(self):
        """Remove exactly one CSV record without rewriting retained records."""
        path = self.root / "index.csv"
        original = b'\xef\xbb\xbfuuid,filename,note\r\none,one.jpg,"two\r\nlines"\r\ntwo,two.jpg,untouched\r\n'
        path.write_bytes(original)
        before, after, row = delete_capture.remove_row(path, "one", "one.jpg")
        self.assertEqual(before, original)
        self.assertEqual(
            after, b"\xef\xbb\xbfuuid,filename,note\r\ntwo,two.jpg,untouched\r\n"
        )
        self.assertEqual(row["note"], "two\r\nlines")
        self.assertEqual(path.read_bytes(), original)

    def test_remove_row_rejects_missing_duplicate_and_filename(self):
        """Reject ambiguous selections before writing any CSV bytes."""
        path = self.root / "index.csv"
        for content, uuid, filename in [
            ("uuid,filename\na,a.jpg\n", "missing", None),
            ("uuid,filename\na,a.jpg\na,a.jpg\n", "a", None),
            ("uuid,filename\na,a.jpg\n", "a", "other.jpg"),
        ]:
            path.write_text(content)
            with self.assertRaises(ValueError):
                delete_capture.remove_row(path, uuid, filename)
            self.assertEqual(path.read_text(), content)

    def test_atomic_write_preserves_mode_and_cleans_failed_temporary(self):
        """Replace files durably and clean temporary files after failed replacement."""
        path = self.root / "atomic.txt"
        delete_capture.atomic_write(path, b"before", 0o640)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        with patch.object(
            delete_capture.os, "replace", side_effect=OSError("fixture failure")
        ):
            with self.assertRaises(OSError):
                delete_capture.atomic_write(path, b"after", 0o600)
        self.assertEqual(path.read_bytes(), b"before")
        self.assertEqual(list(self.root.glob(".atomic.txt.*.tmp")), [])

    def test_delete_removes_both_rows_and_images_only(self):
        """Delete selected images and index rows while preserving other captures and JSON."""
        result = delete_capture.delete_capture(
            self.root, "genuine", self.row["uuid"], self.row["filename"]
        )
        self.assertEqual(result["removed_from"], list(INDEXES))
        self.assertEqual(len(result["deleted_images"]), 2)
        self.assertEqual(
            (result["json_preserved"], result["backup_created"]), (True, False)
        )
        for name in INDEXES:
            with (self.folder / name).open() as stream:
                self.assertEqual(
                    [r["uuid"] for r in csv.DictReader(stream)], [self.rows[1]["uuid"]]
                )
        self.assertTrue((self.folder / self.rows[1]["ori_path"]).exists())
        self.assertTrue(
            (
                self.folder
                / "mykadfront/datacollector_annotation"
                / f"{self.row['uuid']}.json"
            ).exists()
        )

    def test_delete_validation_does_not_modify_indexes(self):
        """Reject invalid folders, filenames, and outside-image paths before deletion."""
        before = (self.folder / INDEXES[0]).read_bytes()
        for folder, uuid, filename in [
            ("../genuine", "x", "x.jpg"),
            ("missing", "x", "x.jpg"),
            ("genuine", self.row["uuid"], "different.jpg"),
        ]:
            with self.assertRaises(ValueError):
                delete_capture.delete_capture(self.root, folder, uuid, filename)
        self.assertEqual((self.folder / INDEXES[0]).read_bytes(), before)

    def test_edit_validates_fields_values_and_conflicts(self):
        """Reject invalid values, protected columns, and stale metadata snapshots."""
        for changes in (
            {},
            [],
            {"ori_path": "outside"},
            {"lighting": "invalid"},
            {"subject": " "},
            {"user": 12},
            {"user": "x" * 4097},
        ):
            with self.subTest(changes_type=type(changes).__name__):
                with self.assertRaises(ValueError):
                    self.edit(changes)
        with self.assertRaises(edit_capture.Conflict):
            self.edit({"lighting": "office-white"}, {**self.row, "subject": "stale"})

    def test_edit_updates_secondary_schema_and_preserves_unrelated_files(self):
        """Add edited columns to the secondary index while keeping images unchanged."""
        before = (self.folder / self.row["ori_path"]).read_bytes()
        self.assertEqual(
            self.edit({"lighting": "office-white"}),
            dict(
                updated=True, changes={"lighting": "office-white"}, json_preserved=True
            ),
        )
        for name in INDEXES:
            with (self.folder / name).open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["lighting"], "office-white")
        self.assertEqual((self.folder / self.row["ori_path"]).read_bytes(), before)

    def test_edit_rolls_back_when_second_write_fails(self):
        """Restore the first CSV when replacement of the second CSV fails."""
        original = {name: (self.folder / name).read_bytes() for name in INDEXES}
        write = edit_capture.atomic_write
        calls = []

        def fail_second(path, data, mode):
            """Fail only the second replacement so rollback can complete."""
            calls.append(path)
            if len(calls) == 2:
                raise OSError("fixture failure")
            write(path, data, mode)

        with patch.object(edit_capture, "atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.edit({"lighting": "office-white"})
        self.assertEqual(
            {name: (self.folder / name).read_bytes() for name in INDEXES}, original
        )

    def test_quality_failure_restores_indexes(self):
        """Restore annotation bytes if persisting the quality review fails."""
        path = self.root / "reviews.json"
        row = dict(
            key=f"genuine/{self.row['uuid']}/{self.row['filename']}",
            folder="genuine",
            metadata=self.row,
        )
        original = {name: (self.folder / name).read_bytes() for name in INDEXES}
        self.assertEqual(quality_reviews.read_reviews(path), {})
        write = quality_reviews.atomic_write

        def fail_review(target, content, mode):
            """Fail review persistence while allowing index rollback writes."""
            if target == path:
                raise OSError("fixture failure")
            write(target, content, mode)

        with patch.object(quality_reviews, "atomic_write", side_effect=fail_review):
            with self.assertRaises(OSError):
                quality_reviews.save_review(path, row, "pass", "", None, self.root)
        self.assertEqual(
            {name: (self.folder / name).read_bytes() for name in INDEXES}, original
        )

    def test_quality_notes_validation(self):
        """Reject oversized or non-text quality notes."""
        row = dict(key="fixture", folder="genuine", metadata=self.row)
        for notes in (None, "x" * 4097):
            with self.assertRaises(ValueError):
                quality_reviews.save_review(
                    self.root / "reviews.json", row, "pass", notes, None, self.root
                )


class IngestionEdgeTests(unittest.TestCase):
    """Characterize scanner recovery, device parsing, and export behavior."""

    def setUp(self):
        """Allocate an isolated scanner database and dataset."""
        temporary = tempfile.TemporaryDirectory(prefix="ingestion-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        dataset(self.root, count=2)
        self.log = ingestion.IngestionLog(self.root, self.root / "history.sqlite")
        self.addCleanup(self.log.db.close)

    def test_device_info_fallbacks_and_timestamp(self):
        """Preserve device fallbacks and timezone-aware UTC timestamps."""
        for row, expected in [
            ({}, ("app", "unknown")),
            ({"input_sensor": "{}"}, ("app", "unknown")),
            ({"input_sensor": "['value']"}, ("app", "['value']")),
            ({"capture_device": " device "}, ("web", "device")),
            ({"input_sensor": "{'model': 123}"}, ("app", "123")),
        ]:
            self.assertEqual(ingestion.device_info(row), expected)
        self.assertTrue(ingestion.now().endswith("+00:00"))

    def test_export_actions_retry_after_write_failure(self):
        """Keep committed audit events and export them on a later successful scan."""
        with patch.object(
            self.log, "export_actions", side_effect=OSError("fixture failure")
        ):
            self.log.record_action("deleted", "genuine", "capture-0", "capture-0.jpg")
        self.assertTrue(self.log.actions_pending)
        self.assertEqual(self.log.snapshot()["action_total"], 1)
        self.log.scan()
        self.assertFalse(self.log.actions_pending)
        self.assertEqual(
            json.loads((self.root / "actions.jsonl").read_text())["action"], "deleted"
        )
        with self.assertRaises(ValueError):
            self.log.record_action("invalid", "genuine", "capture-0", "capture-0.jpg")

    def test_empty_images_and_outside_paths_are_not_ingested(self):
        """Defer empty images and report path escapes without following them."""
        image = self.root / "genuine/mykadfront/orig/capture-0.jpg"
        image.write_bytes(b"")
        self.log.scan()
        self.assertEqual(
            (self.log.snapshot()["total"], self.log.snapshot()["pending_images"]),
            (1, 1),
        )
        image.unlink()
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"fixture")
        image.symlink_to(outside)
        self.log.scan()
        self.assertIn("Image path outside batch", self.log.snapshot()["errors"][0])

    def test_missing_root_reports_scan_error(self):
        """Report an unavailable data root without discarding stored events."""
        self.log.scan()
        self.log.root = self.root / "missing"
        self.log.scan()
        snapshot = self.log.snapshot()
        self.assertEqual(snapshot["total"], 2)
        self.assertTrue(snapshot["errors"])
        self.assertFalse(snapshot["scanning"])


if __name__ == "__main__":
    unittest.main()
