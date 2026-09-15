"""HTTP interface for capture review, with explicit startup and shutdown."""

import hmac
import json
import logging
import mimetypes
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from capture_data import annotation_path, batches, matrix, records
from delete_capture import delete_capture
from edit_capture import Conflict, edit_capture
from ingestion import IngestionLog, with_current_metadata
from quality_reviews import read_reviews, save_review
from settings import Settings

LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 1024 * 1024
STATIC_FILES = {
    "/": "index.html",
    "/coverage.html": "coverage.html",
    "/quality.html": "quality.html",
    "/search.html": "search.html",
    "/ingestion.html": "ingestion.html",
    "/capture_review.js": "capture_review.js",
    "/image_zoom.js": "image_zoom.js",
    "/terminal.css": "terminal.css",
    "/frozen_panes.css": "frozen_panes.css",
}
WRITE_ROUTES = {"/api/apply-decisions", "/api/edit-capture", "/api/quality"}
CONTENT_TYPES = {"html": "text/html", "js": "text/javascript", "css": "text/css"}


class Application:
    """Coordinate dataset access and persistent review state under a shared lock."""

    def __init__(self, settings):
        """Create application state without starting background work."""
        self.settings = settings
        self.lock = threading.RLock()
        self.ingestion = IngestionLog(
            settings.root, settings.database, self.lock, settings.log_path
        )
        self.quality_path = settings.log_path.with_name("quality_reviews.json")

    def records(self):
        """Read the current annotation rows for this application's dataset."""
        return records(self.settings.root)

    def edit(self, request):
        """Apply a metadata edit and persist its action history while holding the lock."""
        with self.lock:
            result = edit_capture(
                self.settings.root,
                request.get("folder", ""),
                request.get("uuid", ""),
                request.get("filename", ""),
                request.get("changes"),
                request.get("expected"),
            )
            changes = {
                key: {"from": request["expected"].get(key, ""), "to": value}
                for key, value in request["changes"].items()
            }
            self.ingestion.record_action(
                "modified",
                request["folder"],
                request["uuid"],
                request["filename"],
                changes,
            )
            return result

    def review(self, request):
        """Save a quality decision only if its capture and expected review still exist."""
        with self.lock:
            row = next(
                (row for row in self.records() if row["key"] == request.get("key")),
                None,
            )
            if row is None:
                raise Conflict("Capture no longer exists")
            return save_review(
                self.quality_path,
                row,
                request.get("status"),
                request.get("notes", ""),
                request.get("expected"),
                self.settings.root,
            )

    def remove(self, request):
        """Validate the entire deletion selection before deleting captures and logging actions."""
        items = request.get("remove", [])
        if not isinstance(items, list) or not items or len(items) > 500:
            raise ValueError("No valid remove decisions")
        if request.get("confirm_count") != len(items):
            raise ValueError("Confirmation count does not match")
        keys = [item.get("key", "") for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate decisions are not allowed")
        with self.lock:
            current = {row["key"]: row for row in self.records()}
            for item in items:
                key = "/".join(
                    item.get(field, "") for field in ("folder", "uuid", "filename")
                )
                if item.get("key") != key or key not in current:
                    raise Conflict(
                        "A selected capture changed or is missing; refresh and review again"
                    )
            results = []
            for item in items:
                results.append(
                    delete_capture(
                        self.settings.root,
                        item["folder"],
                        item["uuid"],
                        item["filename"],
                    )
                )
                self.ingestion.record_action(
                    "deleted", item["folder"], item["uuid"], item["filename"]
                )
            return {"deleted": len(results), "results": results}


class Handler(BaseHTTPRequestHandler):
    """Serve the existing public API and an explicit allowlist of static assets."""

    @property
    def app(self):
        """Access the application attached to this server instance."""
        return self.server.application

    def log_message(self, format, *args):
        """Keep request paths, bodies, credentials, and personal data out of access logs."""
        LOGGER.info("Handled %s request", self.command)

    def send(self, data, kind="application/json", status=200):
        """Send response bytes with the platform's cache and browser-security headers."""
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value):
        """Serialize API data using the existing JSON encoding defaults."""
        self.send(json.dumps(value).encode())

    def do_GET(self):
        """Dispatch a read request and return a generic error for unexpected failures."""
        try:
            url = urlparse(self.path)
            self.get_route(url.path, parse_qs(url.query))
        except Exception as error:
            LOGGER.error("Read request failed (%s)", type(error).__name__)
            self.send(b"Request failed", "text/plain", 500)

    def get_route(self, path, query):
        """Resolve static pages, collection APIs, and individual capture resources."""
        if path in STATIC_FILES:
            filename = STATIC_FILES[path]
            kind = CONTENT_TYPES[filename.rsplit(".", 1)[-1]]
            return self.send(
                (self.app.settings.static_root / filename).read_bytes(),
                kind + "; charset=utf-8",
            )
        if path == "/health":
            return self.send(b'{"ok":true}')
        if path == "/api/captures":
            return self.send_json(self.app.records())
        if path == "/api/matrix":
            return self.send_json(matrix(self.app.settings.root))
        if path == "/api/batches":
            return self.send_json(batches(self.app.settings.root))
        if path == "/api/quality":
            with self.app.lock:
                return self.send_json(read_reviews(self.app.quality_path))
        if path == "/api/search":
            return self.search(query)
        if path == "/api/ingestion":
            return self.ingestion_snapshot(query)
        if path in {"/api/image", "/api/annotation", "/api/capture"}:
            return self.capture_resource(path, query)
        self.send(b"Not found", "text/plain", 404)

    def search(self, query):
        """Search capture identifiers and filenames with the existing result cap."""
        term = query.get("q", [""])[0].strip().lower()
        if not term or len(term) > 200:
            return self.send(
                b"Enter an image ID or filename (up to 200 characters)",
                "text/plain",
                400,
            )
        matches = [
            row
            for row in self.app.records()
            if any(
                term in row["metadata"].get(field, "").lower()
                for field in ("uuid", "filename")
            )
        ]
        self.send_json({"total": len(matches), "results": matches[:100]})

    def ingestion_snapshot(self, query):
        """Validate pagination and overlay current annotations on immutable history."""
        try:
            limit = max(1, min(500, int(query.get("limit", ["100"])[0])))
            before = int(query["before"][0]) if "before" in query else None
        except ValueError:
            return self.send(b"Invalid pagination", "text/plain", 400)
        with self.app.lock:
            result = with_current_metadata(
                self.app.ingestion.snapshot(limit, before), self.app.records()
            )
        self.send_json(result)

    def capture_resource(self, route, query):
        """Return capture metadata or a file confined to the selected capture's folder."""
        row = next(
            (
                row
                for row in self.app.records()
                if row["key"] == query.get("key", [""])[0]
            ),
            None,
        )
        if row is None:
            return self.send(b"Capture not found", "text/plain", 404)
        if route == "/api/capture":
            return self.send_json(row)
        folder = (self.app.settings.root / row["folder"]).resolve()
        path = (
            folder / row["metadata"].get("ori_path", "")
            if route == "/api/image"
            else annotation_path(folder, row["metadata"]["uuid"])
        )
        path = path.resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            return self.send(b"File not found", "text/plain", 404)
        self.send(
            path.read_bytes(),
            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )

    def do_POST(self):
        """Authenticate writes before reading their bounded JSON bodies."""
        try:
            path = urlparse(self.path).path
            if path not in WRITE_ROUTES:
                return self.send(b"Not found", "text/plain", 404)
            if not hmac.compare_digest(
                self.headers.get("X-Delete-Token", ""), self.app.settings.delete_token
            ):
                return self.send(b"Invalid deletion PIN", "text/plain", 403)
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= MAX_REQUEST_BYTES:
                return self.send(b"Invalid request size", "text/plain", 400)
            request = json.loads(self.rfile.read(size))
            action = {
                "/api/quality": self.app.review,
                "/api/edit-capture": self.app.edit,
                "/api/apply-decisions": self.app.remove,
            }[path]
            self.send_json(action(request))
        except Conflict as error:
            self.send(str(error).encode(), "text/plain", 409)
        except ValueError as error:
            self.send(str(error).encode(), "text/plain", 400)
        except Exception as error:
            LOGGER.error("Write request failed (%s)", type(error).__name__)
            self.send(
                b"Batch deletion failed; refresh before retrying", "text/plain", 500
            )


def create_server(settings):
    """Construct an HTTP server without starting its serving loop or ingestion worker."""
    server = ThreadingHTTPServer((settings.host, settings.port), Handler)
    try:
        server.application = Application(settings)
    except Exception:
        server.server_close()
        raise
    return server


def main():
    """Start the configured service and close its worker and database on shutdown."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    def stop_service(signum, frame):
        """Let Docker's termination signal run the normal resource cleanup path."""
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_service)
    server = create_server(Settings.from_environment())
    try:
        server.application.ingestion.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.application.ingestion.close()


if __name__ == "__main__":
    main()
