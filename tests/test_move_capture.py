"""Batch moves use disposable CSVs, images, annotations and review history."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.captures import moving
from app.captures.editing import Conflict
from tests.support import (
    INDEXES,
    IMAGE,
    dataset,
    fixture_naming,
    write_csv,
    running_server,
)


class MoveTests(unittest.TestCase):
    """Check consistent moves and exact restoration after rejected or failed writes."""

    def setUp(self):
        """Create five dummy captures and an existing target with a distinct schema."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = dataset(self.root)
        self.row = dict(self.rows[0], batch="genuine")
        write_csv(self.root / "genuine" / INDEXES[0], [self.row, *self.rows[1:]])
        self.destination = self.root / "destination"
        self.destination.mkdir()
        for name in INDEXES:
            write_csv(
                self.destination / name,
                [dict(uuid="other", filename="other.jpg", batch_name="destination")],
            )
        self.quality = self.root / "quality_reviews.json"
        self.old_key = "genuine/capture-0/capture-0.jpg"
        self.new_key = "destination/capture-0/capture-0.jpg"
        self.review = dict(
            key=self.old_key,
            folder="genuine",
            status="pass",
            notes="Reviewed dummy",
            reviewed_at="unchanged",
        )
        self.quality.write_text(json.dumps({self.old_key: self.review}))
        self.batches = [
            dict(batch_name=name, test_plan_name=self.row["test_plan_name"])
            for name in ("genuine", "destination", "empty")
        ]

    def snapshot(self):
        """Fingerprint every fixture file to detect partial writes or data loss."""
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }

    def move(self, **overrides):
        """Move the selected synthetic capture using production validation."""
        options = dict(
            root=self.root,
            folder_name="genuine",
            uuid="capture-0",
            filename="capture-0.jpg",
            destination="destination",
            changes={},
            expected=self.row,
            batches=self.batches,
            naming=fixture_naming()(),
            quality_path=self.quality,
        )
        options.update(overrides)
        return moving.move_capture(**options)

    def test_move_preserves_images_annotation_csvs_and_review(self):
        """Move both CSV rows and binary assets while retaining unrelated captures."""
        before = self.snapshot()
        result = self.move(changes={"capture_env_lighting": "office-white"})
        self.assertEqual(result["key"], self.new_key)
        for name in INDEXES:
            with (self.root / "genuine" / name).open() as stream:
                source_rows = list(csv.DictReader(stream))
            self.assertEqual(len(source_rows), 4)
            self.assertNotIn("capture-0", [r["uuid"] for r in source_rows])
            with (self.destination / name).open() as stream:
                target_rows = list(csv.DictReader(stream))
            self.assertEqual(len(target_rows), 2)
            self.assertEqual(target_rows[0]["uuid"], "other")
            self.assertEqual(target_rows[0]["batch_name"], "destination")
            row = target_rows[1]
            self.assertEqual(row["capture_env_lighting"], "office-white")
            self.assertEqual(
                row.get("test_plan_name", ""),
                self.row["test_plan_name"] if name == INDEXES[0] else "",
            )
            if name == INDEXES[0]:
                self.assertEqual(row["batch"], "destination")
        for suffix in (
            "orig/capture-0.jpg",
            "crop/capture-0.png",
            "datacollector_annotation/capture-0.json",
        ):
            old = "genuine/mykadfront/" + suffix
            new = "destination/mykadfront/" + suffix
            self.assertFalse((self.root / old).exists())
            self.assertEqual(
                hashlib.sha256((self.root / new).read_bytes()).digest(),
                hashlib.sha256(before[old]).digest(),
            )
        for path, content in before.items():
            if (
                "capture-0" not in path
                and path != "quality_reviews.json"
                and not path.endswith(".csv")
            ):
                self.assertEqual((self.root / path).read_bytes(), content)
        reviews = json.loads(self.quality.read_text())
        self.assertNotIn(self.old_key, reviews)
        self.assertEqual(
            reviews[self.new_key],
            dict(self.review, key=self.new_key, folder="destination"),
        )

    def test_empty_batch_creates_indexes_and_reverse_move_works(self):
        """Create an uncollected destination, then move back without changing assets."""
        before = self.snapshot()
        self.move(destination="empty")
        with (self.root / "empty" / INDEXES[0]).open() as stream:
            row = next(csv.DictReader(stream))
        self.move(folder_name="empty", destination="genuine", expected=row)
        for path, content in before.items():
            if not path.endswith(".csv") and path != "quality_reviews.json":
                self.assertEqual((self.root / path).read_bytes(), content)
        for name in INDEXES:
            with (self.root / "genuine" / name).open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 5)
        self.assertIn(self.old_key, json.loads(self.quality.read_text()))

    def test_stale_illegal_and_collision_leave_all_bytes_unchanged(self):
        """Reject stale snapshots, cross-plan moves, traversal and duplicate UUIDs."""
        for kwargs in [
            dict(expected=dict(self.row, subject="stale")),
            dict(destination="../outside"),
            dict(destination="unknown"),
            dict(changes={"ori_path": "elsewhere"}),
            dict(
                batches=[
                    self.batches[0],
                    dict(batch_name="destination", test_plan_name="other"),
                ]
            ),
        ]:
            before = self.snapshot()
            with self.assertRaises((Conflict, ValueError)):
                self.move(**kwargs)
            self.assertEqual(self.snapshot(), before)
        write_csv(
            self.destination / INDEXES[1], [dict(uuid="capture-0", ori_path="other")]
        )
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.move()
        self.assertEqual(self.snapshot(), before)

    def test_missing_image_and_destination_file_collision(self):
        """Never discard a capture with missing assets or overwrite target files."""
        image = self.root / "genuine" / self.row["ocr_path"]
        image.unlink()
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.move()
        self.assertEqual(self.snapshot(), before)
        image.write_bytes(IMAGE)
        target = self.destination / self.row["ori_path"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"existing image")
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.move()
        self.assertEqual(self.snapshot(), before)

    def test_index_and_review_write_failures_restore_exact_bytes(self):
        """Inject failure at each write, including quality migration, and compare bytes."""
        original = moving.atomic_write
        for fail_at in range(1, 6):
            before = self.snapshot()
            calls = []

            def fail_once(*args):
                """Fail one transaction write while permitting rollback writes."""
                calls.append(args[0])
                if len(calls) == fail_at:
                    raise OSError("dummy write failure")
                return original(*args)

            with patch.object(moving, "atomic_write", side_effect=fail_once):
                with self.assertRaises(OSError):
                    self.move(destination="empty")
            self.assertEqual(self.snapshot(), before)
            self.assertFalse((self.root / "empty").exists())

    def test_unlink_failure_restores_removed_images_and_csvs(self):
        """Restore a previously removed asset when a later source removal fails."""
        original = Path.unlink
        before = self.snapshot()
        calls = []

        def fail_source(path, *args, **kwargs):
            """Fail only the second source asset removal, leaving cleanup usable."""
            if (
                path.parent.name in {"orig", "crop", "datacollector_annotation"}
                and "genuine" in path.parts
            ):
                calls.append(path)
                if len(calls) == 2:
                    raise OSError("dummy unlink failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail_source):
            with self.assertRaises(OSError):
                self.move()
        self.assertEqual(self.snapshot(), before)

    def test_symlink_destination_rejected(self):
        """Reject a destination symlink even when it points within the fixture root."""
        (self.root / "empty").symlink_to(self.destination, target_is_directory=True)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.move(destination="empty")
        self.assertEqual(self.snapshot(), before)


class MoveApiTests(unittest.TestCase):
    """Exercise a real HTTP move and reopen its dummy image, annotation and review."""

    def test_http_move_and_history(self):
        """Ensure API responses, quality, edits, and audit events survive a batch move."""
        with running_server() as client:
            root = client.root
            row = client.rows[0]
            key = "genuine/" + row["uuid"] + "/" + row["filename"]
            batch_file = next(root.glob("*_batches.csv"))
            write_csv(
                batch_file,
                [
                    dict(batch_name=b, test_plan_name=row["test_plan_name"])
                    for b in ("genuine", "destination")
                ],
            )
            status, review, _ = client.request(
                "/api/quality",
                dict(key=key, status="pass", notes="dummy reviewed", expected=None),
                token=client.token,
            )
            self.assertEqual(status, 200)
            current = client.request("/api/capture?key=" + key)[1]["metadata"]
            status, result, _ = client.request(
                "/api/edit-capture",
                dict(
                    folder="genuine",
                    uuid=row["uuid"],
                    filename=row["filename"],
                    destination_batch="destination",
                    changes={"capture_env_lighting": "office-white"},
                    expected=current,
                ),
                token=client.token,
            )
            self.assertEqual(status, 200, result)
            new_key = result["key"]
            self.assertEqual(client.request("/api/capture?key=" + key)[0], 404)
            self.assertEqual(client.request("/api/image?key=" + new_key)[1], IMAGE)
            self.assertEqual(
                client.request("/api/annotation?key=" + new_key)[1]["uuid"], row["uuid"]
            )
            quality = json.loads((root / "quality_reviews.json").read_text())
            self.assertEqual(quality[new_key]["notes"], "dummy reviewed")
            event = client.request("/api/ingestion")[1]["actions"][0]
            self.assertEqual(
                event["changes"]["batch"], {"from": "genuine", "to": "destination"}
            )
            client.restart()
            self.assertEqual(client.request("/api/image?key=" + new_key)[1], IMAGE)


class ProjectMoveTests(unittest.TestCase):
    """Batch moves use the selected project's definitions in both hosting modes."""

    def test_project_scope_in_folder_and_registered_modes(self):
        """Reject another project's target and retain reviews in the selected project."""
        from tests.test_projects import project_payload
        from tests.test_folder_projects import add_folder

        for folder_mode in (False, True):
            with self.subTest(folder_mode=folder_mode), running_server(
                folder_mode=folder_mode
            ) as client:
                row = client.rows[0]
                if folder_mode:
                    project = add_folder(client, "selected")
                    identifier = "selected"
                    batch_file = project / "plan_batches.csv"
                else:
                    status, result, _ = client.request(
                        "/api/projects", project_payload(client)
                    )
                    self.assertEqual(status, 200)
                    identifier = result["id"]
                    project = client.root / "projects" / identifier
                    # Registered projects store definitions in their JSON document.
                    stored = json.loads(project.with_suffix(".json").read_text())
                    stored["batches"].append(
                        dict(
                            batch_name="destination",
                            test_plan_name=row["test_plan_name"],
                        )
                    )
                    project.with_suffix(".json").write_text(json.dumps(stored))
                if folder_mode:
                    write_csv(
                        batch_file,
                        [
                            dict(batch_name=b, test_plan_name=row["test_plan_name"])
                            for b in ("genuine", "destination")
                        ],
                    )
                query = "?project=" + identifier
                payload = dict(
                    folder="genuine",
                    uuid=row["uuid"],
                    filename=row["filename"],
                    expected=row,
                    changes={},
                    destination_batch="outside",
                )
                self.assertEqual(
                    client.request("/api/edit-capture" + query, payload)[0], 400
                )
                payload["destination_batch"] = "destination"
                status, result, _ = client.request("/api/edit-capture" + query, payload)
                self.assertEqual(status, 200, result)
                self.assertEqual(
                    client.request("/api/capture" + query + "&key=" + result["key"])[0],
                    200,
                )
                self.assertEqual(len(client.request("/api/captures" + query)[1]), 5)
