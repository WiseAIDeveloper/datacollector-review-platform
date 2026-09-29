"""Persistent ingestion history, audit exports, and periodic dataset scanning."""

import json
import os
import csv
import io
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .captures.catalog import EXCLUDED, INDEX_NAME, capture_fields

# Event columns every capture has; naming-file fields are stored in `fields`.
CORE = (
    "id",
    "key",
    "status",
    "detected_at",
    "batch",
    "filename",
    "uuid",
    "sdk",
    "test_plan",
    "creation_time",
)
EVENTS = (
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, key TEXT UNIQUE, "
    "status TEXT, detected_at TEXT, batch TEXT, filename TEXT, uuid TEXT, sdk TEXT, "
    "test_plan TEXT, creation_time TEXT, fields TEXT)"
)


def now():
    """Return a timezone-aware UTC timestamp for a detection or action."""
    return datetime.now(timezone.utc).isoformat()


def logged_fields(naming, row):
    """Read the SDK and every naming-file field of a capture as written."""
    sdk, fields = capture_fields(naming, row, {})
    return sdk, {key: v["raw"] or v["value"] for key, v in fields.items()}


def flatten(row):
    """Show an event with its field values as top-level keys, as the JSONL log does."""
    entry = dict(row)
    return {**json.loads(entry.pop("fields") or "{}"), **entry}


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
    if any(None in row or None in row.values() for row in rows):
        raise ValueError("Incomplete CSV row; retrying next scan")
    return rows


class IngestionLog:
    """Persist capture detections and actions without changing historical metadata."""

    def __init__(self, root, database, naming, dataset_lock=None, log_path=None):
        """Open the history database and initialize scanner state without starting a worker.

        `naming` returns the current naming document, whose fields are logged.
        """
        self.naming = naming
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
        self.db.execute(EVENTS)
        self.move_columns_to_fields()
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
        self.batch_filter = None

    def move_columns_to_fields(self):
        """Move each older per-field column into `fields`, keeping its column name."""
        columns = [row[1] for row in self.db.execute("PRAGMA table_info(events)")]
        if "fields" in columns:
            return
        extra = [column for column in columns if column not in CORE]
        rows = [dict(row) for row in self.db.execute("SELECT * FROM events")]
        self.db.execute("ALTER TABLE events RENAME TO events_before_fields")
        self.db.execute(EVENTS)
        for row in rows:
            fields = {column: row.pop(column) or "" for column in extra}
            self.insert_event(row, fields)
        self.db.execute("DROP TABLE events_before_fields")

    def insert_event(self, row, fields):
        """Insert one event from its core values and field values."""
        columns = [c for c in CORE if c in row] + ["fields"]
        values = [row[c] for c in CORE if c in row] + [json.dumps(fields)]
        return self.db.execute(
            f"INSERT OR IGNORE INTO events ({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            values,
        )

    def restore_logs(self):
        """Import copied JSONL history once, transactionally, before the first scan."""
        with self.lock, self.db:
            if self.db.execute(
                "SELECT 1 FROM meta WHERE key='logs_restored'"
            ).fetchone():
                return
            if (
                self.db.execute("SELECT count(*) FROM events").fetchone()[0]
                or self.db.execute("SELECT count(*) FROM actions").fetchone()[0]
            ):
                self.db.execute("INSERT INTO meta VALUES ('logs_restored', '1')")
                return
            restored = 0
            for table, path in (
                ("events", self.log_path),
                ("actions", self.log_path.with_name("actions.jsonl")),
            ):
                if not path.exists():
                    continue
                fields = [
                    row[1] for row in self.db.execute(f"PRAGMA table_info({table})")
                ]
                if table == "events":
                    fields = list(CORE)
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        if not isinstance(row, dict) or not set(fields).issubset(row):
                            raise ValueError(
                                f"Invalid copied {path.name}; history was not imported"
                            )
                        if table == "events":
                            core = {c: row.pop(c) for c in CORE}
                            self.insert_event(core, row)
                            restored += 1
                            continue
                        row["changes"] = json.dumps(row["changes"])
                        self.db.execute(
                            f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                            [row[field] for field in fields],
                        )
                        restored += 1
            if restored:
                self.db.execute(
                    "INSERT OR IGNORE INTO meta VALUES ('initialized', '1')"
                )
            self.db.execute("INSERT INTO meta VALUES ('logs_restored', '1')")

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
            allowed = self.batch_filter() if self.batch_filter else None
            naming = self.naming()
            for folder in folders:
                path = folder / INDEX_NAME
                if (
                    folder.name in EXCLUDED
                    or not path.is_file()
                    or folder.resolve().parent != self.root
                ):
                    continue
                try:
                    rows = read_stable_rows(path)
                    for row in rows:
                        if (
                            allowed is not None
                            and (folder.name, row.get("test_plan_name", ""))
                            not in allowed
                        ):
                            continue
                        uuid, filename = row["uuid"], row["filename"]
                        if not uuid or not filename or not row["ori_path"]:
                            continue
                        image = (folder / row["ori_path"]).resolve()
                        if not image.is_relative_to(folder.resolve()):
                            raise ValueError("Image path outside batch")
                        if not image.is_file() or image.stat().st_size == 0:
                            pending += 1
                            continue
                        sdk, fields = logged_fields(naming, row)
                        result = self.insert_event(
                            dict(
                                key=folder.name + "/" + uuid + "/" + filename,
                                status="existing" if baseline else "ingested",
                                detected_at=detected,
                                batch=folder.name,
                                filename=filename,
                                uuid=uuid,
                                sdk=sdk,
                                test_plan=row.get("test_plan_name", ""),
                                creation_time=row.get("creation_time", ""),
                            ),
                            fields,
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
                stream.write(json.dumps(flatten(row), ensure_ascii=False) + "\n")
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
                dict(r, fields=json.loads(r["fields"] or "{}"))
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

    def newest_event_keys(self):
        """Return all logged capture keys in ingestion order, newest first."""
        with self.lock:
            return [row[0] for row in self.db.execute("SELECT key FROM events ORDER BY id DESC")]

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
            event.update(
                batch=row["folder"],
                sdk=row["sdk"],
                fields=row["fields"],
                naming=row["naming"],
            )
            for name in ("filename", "uuid", "creation_time"):
                event[name] = metadata.get(name, "")
            event["test_plan"] = metadata.get("test_plan_name", "")
        events.append(event)
    return dict(snapshot, events=events)


def possible_excess_keys(records, plan, naming, newest_keys):
    """Identify the newest available captures beyond each matrix row's count."""
    if not plan:
        return set()
    fields = [
        field.key
        for field in naming.fields
        if field.role != "identity" and field.key in plan[0]
    ]
    requirements = {
        (
            row["folder"],
            row["sdk"],
            row.get("test_plan_name", ""),
            *(row[field] for field in fields),
        ): int(row["expected_count_per_identity"])
        for row in plan
    }
    current = {row["key"]: row for row in records}
    groups = {}
    for key in newest_keys:
        record = current.get(key)
        if record is None:
            continue
        requirement = (
            record["folder"],
            record["sdk"],
            record["metadata"].get("test_plan_name", ""),
            *(record["fields"].get(field, "") for field in fields),
        )
        identity = record["fields"].get(naming.identity.key, "")
        if identity and requirement in requirements:
            groups.setdefault((identity, requirement), []).append(key)
    excess = set()
    for (_, requirement), keys in groups.items():
        excess.update(keys[: max(0, len(keys) - requirements[requirement])])
    return excess
