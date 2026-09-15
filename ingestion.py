"""Persistent ingestion history, audit exports, and periodic dataset scanning."""

import ast
import json
import os
import csv
import io
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from capture_data import EXCLUDED


def now():
    """Return a timezone-aware UTC timestamp for a detection or action."""
    return datetime.now(timezone.utc).isoformat()


def device_info(row):
    """Normalize scanner device metadata while retaining its historical fallback rules."""
    cap = (row.get("capture_device") or "").strip()
    if cap:
        return "web", cap
    raw = row.get("input_sensor") or ""
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, dict):
            return "app", str(value.get("model", "unknown"))
    except (ValueError, SyntaxError):
        pass
    return "app", raw.split(",")[0].removeprefix("model:") or "unknown"


def read_stable_rows(path):
    """Read complete annotation rows only when the CSV stays unchanged during the read."""
    before = path.stat()
    text = path.read_text(encoding="utf-8-sig")
    after = path.stat()
    if (before.st_mtime_ns, before.st_size) != (
        after.st_mtime_ns,
        after.st_size,
    ):
        raise ValueError("CSV changed during scan; retrying next scan")
    reader = csv.DictReader(io.StringIO(text), strict=True)
    if not {"uuid", "filename", "ori_path"}.issubset(reader.fieldnames or []):
        raise ValueError("Missing required CSV columns")
    rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Incomplete CSV row; retrying next scan")
    return rows


class IngestionLog:
    """Persist capture detections and actions without changing historical metadata."""

    def __init__(self, root, database, dataset_lock=None, log_path=None):
        """Open the history database and initialize scanner state without starting a worker."""
        self.root = Path(root).resolve()
        self.log_path = (
            Path(log_path) if log_path else Path(database).with_suffix(".jsonl")
        )
        self.export_pending = True
        self.actions_pending = True
        self.lock = threading.RLock()
        self.dataset_lock = dataset_lock or threading.RLock()
        self.db = sqlite3.connect(str(database), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, key TEXT UNIQUE, status TEXT, detected_at TEXT, batch TEXT, filename TEXT, uuid TEXT, lighting TEXT, subject TEXT, sdk TEXT, device TEXT, test_plan TEXT, creation_time TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, action TEXT, occurred_at TEXT, batch TEXT, uuid TEXT, filename TEXT, changes TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self.db.commit()
        self.status = dict(
            last_scan=None,
            interval_seconds=5,
            scanning=True,
            errors=[],
            pending_images=0,
            new_entries=0,
        )
        self.stop = threading.Event()
        self.thread = None

    def scan(self):
        """Log each complete capture once and retry incomplete files on the next scan."""
        with self.dataset_lock, self.lock:
            baseline = (
                self.db.execute(
                    "SELECT value FROM meta WHERE key='initialized'"
                ).fetchone()
                is None
            )
            errors, pending, added = [], 0, 0
            detected = now()
            try:
                folders = sorted(self.root.iterdir())
            except OSError as e:
                self.status.update(last_scan=detected, scanning=False, errors=[str(e)])
                return
            for folder in folders:
                path = folder / "index_annotation_.csv"
                if (
                    folder.name in EXCLUDED
                    or not path.is_file()
                    or folder.resolve().parent != self.root
                ):
                    continue
                try:
                    rows = read_stable_rows(path)
                    for row in rows:
                        uuid, filename = row["uuid"], row["filename"]
                        if not uuid or not filename or not row["ori_path"]:
                            continue
                        image = (folder / row["ori_path"]).resolve()
                        if not image.is_relative_to(folder.resolve()):
                            raise ValueError("Image path outside batch")
                        if not image.is_file() or image.stat().st_size == 0:
                            pending += 1
                            continue
                        sdk, device = device_info(row)
                        key = folder.name + "/" + uuid + "/" + filename
                        result = self.db.execute(
                            "INSERT OR IGNORE INTO events (key,status,detected_at,batch,filename,uuid,lighting,subject,sdk,device,test_plan,creation_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                key,
                                "existing" if baseline else "ingested",
                                detected,
                                folder.name,
                                filename,
                                uuid,
                                row.get("lighting", ""),
                                row.get("subject", ""),
                                sdk,
                                device,
                                row.get("test_plan_name", ""),
                                row.get("creation_time", ""),
                            ),
                        )
                        added += result.rowcount
                except (OSError, ValueError, csv.Error) as e:
                    errors.append(folder.name + ": " + str(e))
            if not errors:
                self.db.execute(
                    "INSERT OR IGNORE INTO meta VALUES ('initialized', '1')"
                )
            self.db.commit()
            self.export_pending = (
                self.export_pending or added > 0 or not self.log_path.exists()
            )
            if self.export_pending:
                self.export_log()
            if (
                self.actions_pending
                or not self.log_path.with_name("actions.jsonl").exists()
            ):
                self.export_actions()
            self.status.update(
                last_scan=detected,
                scanning=False,
                errors=errors,
                pending_images=pending,
                new_entries=added,
            )

    def export_log(self):
        """Atomically export capture history in insertion order to the JSONL log."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.log_path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            for row in self.db.execute("SELECT * FROM events ORDER BY id"):
                stream.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.log_path)
        self.export_pending = False

    def export_actions(self):
        """Atomically export recorded edits and deletions with decoded change details."""
        path = self.log_path.with_name("actions.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            for row in self.db.execute("SELECT * FROM actions ORDER BY id"):
                entry = dict(row)
                entry["changes"] = json.loads(entry["changes"])
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        self.actions_pending = False

    def record_action(self, action, batch, uuid, filename, changes=None):
        """Commit an audit event and defer failed file exports to the next scan."""
        if action not in {"modified", "deleted"}:
            raise ValueError("Invalid action")
        with self.lock:
            self.db.execute(
                "INSERT INTO actions (action,occurred_at,batch,uuid,filename,changes) VALUES (?,?,?,?,?,?)",
                (action, now(), batch, uuid, filename, json.dumps(changes or {})),
            )
            self.db.commit()
            self.actions_pending = True
            try:
                self.export_actions()
            except OSError:
                # The committed DB record is retried to the physical file next scan.
                pass

    def snapshot(self, limit=100, before=None):
        """Return paginated history, aggregate counts, and the latest fifty actions."""
        with self.lock:
            where, args = ("WHERE id < ?", [before]) if before else ("", [])
            records = [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM events " + where + " ORDER BY id DESC LIMIT ?",
                    args + [limit],
                )
            ]
            counts = dict(
                self.db.execute("SELECT status, count(*) FROM events GROUP BY status")
            )
            actions = [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM actions ORDER BY id DESC LIMIT 50"
                )
            ]
            for action in actions:
                action["changes"] = json.loads(action["changes"])
            action_total = self.db.execute("SELECT count(*) FROM actions").fetchone()[0]
            return dict(
                self.status,
                actions=actions,
                action_total=action_total,
                events=records,
                total=sum(counts.values()),
                existing=counts.get("existing", 0),
                ingested=counts.get("ingested", 0),
                next_before=records[-1]["id"] if len(records) == limit else None,
            )

    def run(self):
        """Scan every five seconds until stopped, retaining database errors for the API."""
        while not self.stop.is_set():
            try:
                self.scan()
            except Exception as e:
                with self.lock:
                    self.db.rollback()
                    self.status.update(last_scan=now(), scanning=False, errors=[str(e)])
            self.stop.wait(5)

    def start(self):
        """Start a single background scanner thread for this ingestion log."""
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.stop.clear()
                self.thread = threading.Thread(
                    target=self.run, name="ingestion-scanner", daemon=True
                )
                self.thread.start()

    def close(self):
        """Stop the scanner before closing its shared SQLite connection."""
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        with self.lock:
            self.db.close()


def with_current_metadata(snapshot, records):
    """Overlay live CSV values on an API response; never change stored history."""
    current = {row["key"]: row for row in records}
    events = []
    for original in snapshot["events"]:
        event = dict(original)
        row = current.get(event["key"])
        event["available"] = row is not None
        if row is not None:
            metadata = row["metadata"]
            event.update(batch=row["folder"], sdk=row["sdk"], device=row["device"])
            for name in ("filename", "uuid", "lighting", "subject", "creation_time"):
                event[name] = metadata.get(name, "")
            event["test_plan"] = metadata.get("test_plan_name", "")
        events.append(event)
    return dict(snapshot, events=events)
