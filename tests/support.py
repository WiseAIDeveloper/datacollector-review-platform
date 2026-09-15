"""Disposable datasets and HTTP servers shared by regression tests."""

import base64
import csv
import importlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("REVIEW_SOURCE", PROJECT)).resolve()
sys.path.insert(0, str(SOURCE))
MODULES = {
    "server": "app.server",
    "settings": "app.settings",
    "capture_data": "app.captures.catalog",
    "delete_capture": "app.captures.deletion",
    "edit_capture": "app.captures.editing",
    "quality_reviews": "app.captures.quality",
    "ingestion": "app.ingestion",
}
MATRIX_NAME = "internal_colour_print_enhancement_2"
INDEXES = ("index_annotation_.csv", "index_annotation_mykadfront.csv")
IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF9sAAAAASUVORK5CYII="
)


def application_module(name, source=SOURCE):
    """Resolve the module name for either a packaged or historical flat checkout."""
    return MODULES[name] if (source / "app").is_dir() else name


def load_application(name):
    """Import the selected implementation so compatibility tests share assertions."""
    return importlib.import_module(application_module(name))


def application_command(name, source=SOURCE):
    """Launch the packaged entry point or the equivalent historical script."""
    if (source / "app").is_dir():
        module = "app" if name == "server" else MODULES[name]
        return [sys.executable, "-m", module]
    return [sys.executable, str(source / (name + ".py"))]


def asset_path(source, filename):
    """Locate a public asset without changing its browser URL across source layouts."""
    if not (source / "web").is_dir():
        return source / filename
    suffix = Path(filename).suffix
    directory = "pages" if suffix == ".html" else "static/" + suffix.lstrip(".")
    return source / "web" / directory / filename


def write_csv(path, rows, fields=None):
    """Write fixture rows with deterministic CSV headers and line endings."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dataset(root, count=5):
    """Create synthetic captures, images, annotations, and dashboard definitions."""
    folder = root / "genuine"
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(count):
        uuid = f"capture-{index}"
        row = dict(
            uuid=uuid,
            filename=f"{uuid}.jpg",
            subject="fixture",
            lighting="dark",
            capture_device="iphone-13",
            input_sensor="",
            user="fixture-user",
            ori_path=f"mykadfront/orig/{uuid}.jpg",
            ocr_path=f"mykadfront/crop/{uuid}.png",
            test_plan_name="colour_print_enhancement_2",
            creation_time="2026-01-01T00:00:00Z",
        )
        rows.append(row)
        for field in ("ori_path", "ocr_path"):
            image = folder / row[field]
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(IMAGE)
        annotation = folder / "mykadfront/datacollector_annotation" / f"{uuid}.json"
        annotation.parent.mkdir(parents=True, exist_ok=True)
        annotation.write_text(json.dumps({"lighting": "office-white", "uuid": uuid}))
    write_csv(folder / INDEXES[0], rows)
    write_csv(
        folder / INDEXES[1],
        [{k: r[k] for k in ("uuid", "ori_path", "ocr_path")} for r in rows],
    )
    write_csv(
        root / f"{MATRIX_NAME}.csv",
        [
            dict(
                matrix_name=MATRIX_NAME,
                folder="genuine",
                lighting="dark",
                sdk="web",
                device="iphone-13",
                expected_count_per_identity=str(count),
            )
        ],
    )
    write_csv(
        root / f"{MATRIX_NAME}_batches.csv",
        [
            dict(
                batch_name="genuine",
                test_plan_name="colour_print_enhancement_2",
                expected_lighting="dark;office-white;office-yellow",
                expected_identities="fixture;another",
                expected_web_devices="iphone-13",
            )
        ],
    )
    return rows


class Client:
    """Send requests directly to an isolated test server without ambient proxies."""

    def __init__(self, base, token, root, rows):
        """Retain the fixture address and disposable authentication value."""
        self.base, self.token, self.root, self.rows = base, token, root, rows
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(
        self, path, payload=None, token=None, raw=None, method=None, headers=None
    ):
        """Return status, decoded response, and headers for success or failure."""
        data = json.dumps(payload).encode() if payload is not None else raw
        request_headers = dict(headers or {})
        if data is not None:
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault(
                "X-Delete-Token", self.token if token is None else token
            )
        request = urllib.request.Request(
            self.base + path, data=data, headers=request_headers, method=method
        )
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            if response.headers.get_content_type() == "application/json":
                body = json.loads(body)
            return response.status, body, response.headers


class FixtureServer(Client):
    """Manage a restartable server process backed by one disposable dataset."""

    def __init__(self, base, token, root, rows, command, source, environment):
        """Keep process configuration alongside the fixture's HTTP client."""
        super().__init__(base, token, root, rows)
        self.command, self.source, self.environment = command, source, environment
        self.process = None

    def start(self):
        """Launch the selected server and wait for its initial ingestion scan."""
        self.process = subprocess.Popen(
            self.command,
            cwd=self.source,
            env=self.environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for attempt in range(100):
            if self.process.poll() is not None:
                raise RuntimeError("Fixture server exited during startup")
            try:
                if (
                    self.request("/health")[0] == 200
                    and not self.request("/api/ingestion?limit=1")[1]["scanning"]
                ):
                    return
            except OSError:
                pass
            time.sleep(0.05)
        raise RuntimeError("Fixture server did not become ready")

    def stop(self):
        """Terminate the fixture process and bound cleanup if shutdown stalls."""
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def restart(self):
        """Restart the same server without replacing its persisted fixture files."""
        self.stop()
        self.start()


@contextmanager
def running_server(source=SOURCE):
    """Run either the original or current app against disposable data only."""
    with tempfile.TemporaryDirectory(prefix="review-test-") as temporary:
        root = Path(temporary)
        rows = dataset(root)
        token = secrets.token_hex(24)
        pin = root / "pin"
        pin.write_text(token)
        pin.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        server_path = source / (
            application_module("server", source).replace(".", "/") + ".py"
        )
        source_text = server_path.read_text()
        # The original server has no settings or import guard; adapt only its paths and port.
        legacy = "ThreadingHTTPServer(('0.0.0.0',8080)" in source_text
        command = application_command("server", source)
        if legacy:
            script = root / "legacy_server.py"
            script.write_text(
                source_text.replace("'/run/secrets/delete_token'", repr(str(pin)))
                .replace("'/logs/ingestion.jsonl'", repr(str(root / "ingestion.jsonl")))
                .replace("('0.0.0.0',8080)", repr(("127.0.0.1", port)))
                .replace("/app/", str(source) + "/")
            )
            command = [sys.executable, str(script)]
        environment = {
            **os.environ,
            "DATA_ROOT": str(root),
            "INGESTION_DB": str(root / "history.sqlite"),
            "INGESTION_LOG": str(root / "ingestion.jsonl"),
            "DELETE_TOKEN": token,
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "PYTHONPATH": str(source),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        client = FixtureServer(
            f"http://127.0.0.1:{port}",
            token,
            root,
            rows,
            command,
            source,
            environment,
        )
        try:
            client.start()
            yield client
        finally:
            client.stop()
