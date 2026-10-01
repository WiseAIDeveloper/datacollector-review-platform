"""Ensure cached metadata remains equivalent to fresh reads after external changes."""

import copy
import gzip
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app.captures import catalog
from app.captures.naming import Naming
from app.server import Application, accepts_gzip
from tests.support import NAMING, dataset, running_server, write_csv


class CatalogCacheTests(unittest.TestCase):
    """Cache only unchanged file versions and discard deleted entries."""

    def setUp(self):
        """Create disposable rows and an independent cache."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rows = dataset(self.root)
        self.naming = Naming(NAMING)
        self.cache = catalog.CatalogCache(self.root)
        self.index = self.root / "genuine" / catalog.INDEX_NAME
        self.annotation = catalog.annotation_path(self.root / "genuine", "capture-0")

    def assert_current(self):
        """Compare every cached field and ordering with the uncached reader."""
        self.assertEqual(
            self.cache.records(self.naming), catalog.records(self.root, self.naming)
        )

    def test_warm_reads_reuse_annotation_and_normalization(self):
        """Unchanged requests avoid JSON reads and field normalization entirely."""
        self.assert_current()
        with patch.object(
            catalog, "capture_record", side_effect=AssertionError("rebuilt")
        ):
            for _ in range(3):
                self.assertEqual(len(self.cache.records(self.naming)), 5)

    def test_csv_edit_append_reorder_and_delete(self):
        """External CSV updates are visible immediately and retain exact row order."""
        self.assert_current()
        self.rows[0]["subject"] = "updated"
        self.rows.append(dict(self.rows[1], uuid="new", filename="new.jpg"))
        write_csv(self.index, self.rows[::-1])
        self.assert_current()
        write_csv(self.index, self.rows[:2])
        self.assert_current()
        self.assertEqual(len(self.cache.entries), 2)
        self.index.unlink()
        self.assert_current()
        self.assertEqual(self.cache.entries, {})
        self.assertEqual(self.cache.indexes, {})

    def test_annotation_and_naming_updates(self):
        """Same-size edits, replacement, malformed JSON, and naming reload invalidate results."""
        self.assert_current()
        old = self.annotation.stat()
        text = self.annotation.read_text().replace("office-white", "office-black")
        self.annotation.write_text(text)
        os.utime(self.annotation, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assert_current()
        replacement = self.annotation.with_suffix(".tmp")
        replacement.write_text("{")
        replacement.replace(self.annotation)
        self.assert_current()
        self.annotation.unlink()
        self.assert_current()
        self.annotation.write_text(
            json.dumps({"capture_env_lighting": "office-yellow"})
        )
        self.assert_current()
        changed = copy.deepcopy(NAMING)
        changed["capture_env_lighting"]["accepted"] = ["different"]
        self.naming = Naming(changed)
        self.assert_current()

    def test_concurrent_readers_and_independent_datasets(self):
        """Concurrent callers share a build, while another dataset cannot reuse it."""
        expected = catalog.records(self.root, self.naming)
        with patch.object(
            catalog, "capture_record", wraps=catalog.capture_record
        ) as build:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(
                    pool.map(lambda _: self.cache.records(self.naming), range(6))
                )
            self.assertEqual(build.call_count, 5)
        self.assertTrue(all(result == expected for result in results))
        with tempfile.TemporaryDirectory() as other:
            dataset(Path(other), count=1)
            self.assertEqual(len(catalog.CatalogCache(other).records(self.naming)), 1)
        self.assert_current()

    def test_overlapping_requests_share_validation(self):
        """A burst checks files once, while a subsequent request still revalidates them."""
        barrier = threading.Barrier(4)
        lock = threading.Lock()

        class SimultaneousLock:
            """Arrange four overlapping reads without timing-dependent sleeps."""

            def __enter__(self):
                """Let all reads begin before the first can build its snapshot."""
                barrier.wait(timeout=5)
                lock.acquire()

            def __exit__(self, *args):
                """Allow the next waiter to reuse the newly validated snapshot."""
                lock.release()

        self.cache.lock = SimultaneousLock()
        with patch.object(catalog, "file_stamp", wraps=catalog.file_stamp) as stat:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(
                    pool.map(lambda _: self.cache.records(self.naming), range(4))
                )
            self.assertEqual(stat.call_count, 12)
        self.assertTrue(all(result == results[0] for result in results))
        self.cache.lock = threading.RLock()
        self.rows[0]["subject"] = "changed-after-burst"
        write_csv(self.index, self.rows)
        self.assert_current()

    def test_encoded_snapshot_reuse_and_scope(self):
        """Response bytes are shared only while every ordered record is unchanged."""
        application = Application.__new__(Application)
        application.response_lock = threading.Lock()
        application.response_rows = None
        application.response_bytes = None
        rows = self.cache.records(self.naming)
        first = application.encode_captures(rows)
        self.assertIs(application.encode_captures(list(rows)), first)
        subset = application.encode_captures(rows[:1])
        self.assertEqual(len(json.loads(subset[0])), 1)
        self.rows[0]["subject"] = "new-subject"
        write_csv(self.index, self.rows)
        updated = application.encode_captures(self.cache.records(self.naming))
        self.assertEqual(json.loads(updated[0])[0]["identity"], "new-subject")
        self.assertEqual(json.loads(first[0])[0]["identity"], "fixture")


class CompressedJsonTests(unittest.TestCase):
    """Keep old clients working while reducing JSON transfer size for browsers."""

    def test_negotiation_and_round_trip(self):
        """Gzip preserves response data, headers, and explicit compression opt-out."""
        for header, expected in [
            ("gzip, deflate, br", True),
            ("gzip;q=0", False),
            ("gzip;q=0.5", True),
            ("br", False),
            ("gzip;q=invalid", False),
        ]:
            self.assertEqual(accepts_gzip(header), expected)
        with running_server() as client:
            original = client.request("/api/captures")[1]
            request = urllib.request.Request(
                client.base + "/api/captures", headers={"Accept-Encoding": "gzip"}
            )
            with client.opener.open(request) as response:
                compressed = response.read()
                self.assertEqual(response.headers["Content-Encoding"], "gzip")
                self.assertEqual(response.headers["Vary"], "Accept-Encoding")
                self.assertEqual(
                    int(response.headers["Content-Length"]), len(compressed)
                )
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(json.loads(gzip.decompress(compressed)), original)
            self.assertLess(len(compressed), len(json.dumps(original).encode()) // 2)
            request = urllib.request.Request(
                client.base + "/api/captures", headers={"Accept-Encoding": "gzip;q=0"}
            )
            with client.opener.open(request) as response:
                self.assertIsNone(response.headers.get("Content-Encoding"))
                self.assertEqual(json.load(response), original)
