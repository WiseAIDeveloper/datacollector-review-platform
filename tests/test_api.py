"""HTTP contracts exercised unchanged against original and refactored servers."""

import csv
import json
import unittest
from urllib.parse import quote

from tests.support import IMAGE, INDEXES, MATRIX_NAME, SOURCE, running_server


class ApiTests(unittest.TestCase):
    """Verify routes, validation, mutations, and persisted history on fixtures."""

    def setUp(self):
        """Start an isolated server and select its first synthetic capture."""
        self.context = running_server()
        self.client = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.row = self.client.rows[0]
        self.key = f"genuine/{self.row['uuid']}/{self.row['filename']}"

    def test_read_routes_and_headers(self):
        """Preserve health, static assets, capture details, and response headers."""
        status, body, headers = self.client.request("/health")
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        for filename in [
            "index.html",
            "coverage.html",
            "quality.html",
            "search.html",
            "ingestion.html",
            "capture_review.js",
            "image_zoom.js",
            "terminal.css",
            "frozen_panes.css",
        ]:
            path = "/" if filename == "index.html" else "/" + filename
            with self.subTest(path=path):
                status, body, headers = self.client.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(body, (SOURCE / filename).read_bytes())
                self.assertEqual(int(headers["Content-Length"]), len(body))
        status, rows, _ = self.client.request("/api/captures")
        self.assertEqual(status, 200)
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            rows[0],
            dict(
                key=self.key,
                folder="genuine",
                line=2,
                sdk="web",
                device="iphone-13",
                annotation_lighting="office-white",
                metadata=self.row,
            ),
        )
        self.assertEqual(
            self.client.request("/api/capture?key=" + quote(self.key))[1], rows[0]
        )
        self.assertEqual(
            self.client.request("/api/image?key=" + quote(self.key))[1], IMAGE
        )
        self.assertEqual(
            self.client.request("/api/annotation?key=" + quote(self.key))[1],
            {"lighting": "office-white", "uuid": self.row["uuid"]},
        )
        self.assertEqual(
            self.client.request("/api/matrix")[1][0]["matrix_name"], MATRIX_NAME
        )
        self.assertEqual(
            self.client.request("/api/batches")[1][0]["batch_name"], "genuine"
        )

    def test_search_and_not_found(self):
        """Preserve case-insensitive search, query limits, and missing-route errors."""
        self.assertEqual(self.client.request("/api/search?q=CAPTURE-0")[1]["total"], 1)
        self.assertEqual(
            self.client.request("/api/search?q=missing")[1], {"total": 0, "results": []}
        )
        for query in ("", "x" * 201):
            self.assertEqual(self.client.request("/api/search?q=" + query)[0], 400)
        for path in (
            "/missing",
            "/api/capture?key=missing",
            "/api/image?key=missing",
            "/.env",
            "/server.py",
        ):
            self.assertEqual(self.client.request(path)[0], 404)
        self.assertEqual(self.client.request("/missing", {})[0], 404)

    def test_authentication_and_payload_limits(self):
        """Reject unauthenticated writes, malformed JSON, and invalid body sizes."""
        for path in ("/api/quality", "/api/edit-capture", "/api/apply-decisions"):
            self.assertEqual(self.client.request(path, {}, token="")[0], 403)
            self.assertEqual(self.client.request(path, {}, token="invalid")[0], 403)
        self.assertEqual(self.client.request("/api/quality", raw=b"{")[0], 400)
        self.assertEqual(self.client.request("/api/quality", raw=b"")[0], 400)
        self.assertEqual(
            self.client.request(
                "/api/quality", {}, headers={"Content-Length": "1048577"}
            )[0],
            400,
        )

    def test_ingestion_and_pagination(self):
        """Keep ingestion counts, pagination, and live metadata overlays stable."""
        status, snapshot, _ = self.client.request("/api/ingestion?limit=2")
        self.assertEqual(status, 200)
        self.assertEqual(
            (snapshot["total"], snapshot["existing"], snapshot["ingested"]), (5, 5, 0)
        )
        self.assertTrue(all(event["available"] for event in snapshot["events"]))
        next_page = self.client.request(
            f"/api/ingestion?limit=2&before={snapshot['next_before']}"
        )[1]
        self.assertFalse(
            {e["id"] for e in snapshot["events"]}
            & {e["id"] for e in next_page["events"]}
        )
        self.assertEqual(
            len(self.client.request("/api/ingestion?limit=0")[1]["events"]), 1
        )
        for query in ("limit=invalid", "before=invalid"):
            self.assertEqual(self.client.request("/api/ingestion?" + query)[0], 400)

    def test_edit_conflict_and_action_history(self):
        """Apply an edit once, reject stale metadata, and retain its audit record."""
        payload = dict(
            folder="genuine",
            uuid=self.row["uuid"],
            filename=self.row["filename"],
            changes={"lighting": "office-yellow"},
            expected=self.row,
        )
        self.assertEqual(
            self.client.request("/api/edit-capture", payload)[1],
            dict(updated=True, changes=payload["changes"], json_preserved=True),
        )
        self.assertEqual(self.client.request("/api/edit-capture", payload)[0], 409)
        snapshot = self.client.request("/api/ingestion")[1]
        event = next(e for e in snapshot["events"] if e["key"] == self.key)
        self.assertEqual(event["lighting"], "office-yellow")
        self.assertEqual(snapshot["action_total"], 1)
        self.assertEqual(
            snapshot["actions"][0]["changes"],
            {"lighting": {"from": "dark", "to": "office-yellow"}},
        )
        self.assertEqual(
            len((self.client.root / "actions.jsonl").read_text().splitlines()), 1
        )

    def test_delete_validation_and_preserved_history(self):
        """Validate a deletion batch before changing files and preserve annotations."""
        item = dict(
            key=self.key,
            folder="genuine",
            uuid=self.row["uuid"],
            filename=self.row["filename"],
        )
        for payload in (
            {},
            {"remove": "invalid"},
            {"remove": [item], "confirm_count": 0},
            {"remove": [item, item], "confirm_count": 2},
        ):
            self.assertEqual(
                self.client.request("/api/apply-decisions", payload)[0], 400
            )
        self.assertEqual(
            self.client.request(
                "/api/apply-decisions",
                {"remove": [{**item, "key": "stale"}], "confirm_count": 1},
            )[0],
            409,
        )
        status, result, _ = self.client.request(
            "/api/apply-decisions", {"remove": [item], "confirm_count": 1}
        )
        self.assertEqual((status, result["deleted"]), (200, 1))
        self.assertTrue(result["results"][0]["json_preserved"])
        self.assertEqual(
            self.client.request("/api/capture?key=" + quote(self.key))[0], 404
        )
        self.assertTrue(
            (
                self.client.root
                / "genuine/mykadfront/datacollector_annotation"
                / f"{self.row['uuid']}.json"
            ).exists()
        )
        snapshot = self.client.request("/api/ingestion")[1]
        self.assertEqual(snapshot["total"], 5)
        self.assertFalse(
            next(e for e in snapshot["events"] if e["key"] == self.key)["available"]
        )
        self.assertEqual(snapshot["actions"][0]["action"], "deleted")

    def test_quality_validation_conflicts_and_persistence(self):
        """Persist quality transitions in both indexes and reject stale reviews."""
        payload = dict(
            key=self.key, status="error", notes="Synthetic glare", expected=None
        )
        self.assertEqual(
            self.client.request("/api/quality", {**payload, "status": "invalid"})[0],
            400,
        )
        self.assertEqual(
            self.client.request("/api/quality", {**payload, "key": "missing"})[0], 409
        )
        expected = None
        for status, value in (("error", "fail"), ("pass", "pass"), ("unreviewed", "")):
            response, entry, _ = self.client.request(
                "/api/quality", {**payload, "status": status, "expected": expected}
            )
            self.assertEqual((response, entry["status"]), (200, status))
            self.assertEqual(self.client.request("/api/quality")[1][self.key], entry)
            stored = json.loads((self.client.root / "quality_reviews.json").read_text())
            self.assertEqual(stored[self.key], entry)
            for name in INDEXES:
                with (self.client.root / "genuine" / name).open() as stream:
                    self.assertEqual(
                        next(csv.DictReader(stream))["quality_review_status"], value
                    )
            expected = entry
        self.assertEqual(self.client.request("/api/quality", payload)[0], 409)

    def test_quality_and_history_survive_server_restart(self):
        """Preserve saved quality decisions and ingestion history across a process restart."""
        payload = dict(
            key=self.key, status="pass", notes="Synthetic review", expected=None
        )
        status, saved, _ = self.client.request("/api/quality", payload)
        self.assertEqual(status, 200)
        self.client.restart()
        self.assertEqual(self.client.request("/api/quality")[1][self.key], saved)
        snapshot = self.client.request("/api/ingestion")[1]
        self.assertEqual((snapshot["total"], snapshot["existing"]), (5, 5))


if __name__ == "__main__":
    unittest.main()
