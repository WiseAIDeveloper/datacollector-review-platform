"""Rename stored fields (columns and keys) everywhere captures and plans keep them.

Use this when a naming-file field is renamed. Each --rename old=new renames:
capture index CSV headers, collection annotation JSON keys, project plan CSV
headers, each project's ingestion history (field values and edit records), and
the JSONL logs exported from it. Each --merge a,b=new joins two semicolon-list
plan columns into one (for example two per-SDK device lists into
expected_<device field>), keeping the first-seen order.

Runs as a dry run unless --apply is given with a new --backup directory, which
receives a copy of every file before it is replaced. Stop the review service
before applying, since it writes the ingestion history.
"""

import argparse
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.captures.catalog import EXCLUDED
from app.captures.deletion import atomic_write
from app.ingestion import IngestionLog
from scripts.normalize_names import ANNOTATIONS, INDEXES


def pairs(values, label):
    """Parse repeated old=new arguments; for merges, old is a comma-separated list."""
    result = {}
    for value in values:
        old, separator, new = value.partition("=")
        if not separator or not old or not new or old in result:
            raise SystemExit(f"Invalid or repeated {label}: {value}")
        result[old] = new
    return result


def rename_header(text, renames):
    """Rename header cells only; every data row keeps its exact bytes."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return text
    header = next(csv.reader([lines[0]]))
    renamed = [renames.get(name, name) for name in header]
    if renamed == header:
        return text
    if len(set(renamed)) != len(renamed):
        raise ValueError("Renaming would create a duplicate column")
    ending = "\r\n" if lines[0].endswith("\r\n") else "\n"
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=ending).writerow(renamed)
    return buffer.getvalue() + "".join(lines[1:])


def merge_columns(text, merges):
    """Join semicolon-list columns into one column placed where the first was."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    active = {
        new: old.split(",")
        for old, new in merges.items()
        if any(name in header for name in old.split(","))
    }
    if not active:
        return text
    rows = list(reader)
    for new, sources in active.items():
        if new in header:
            raise ValueError(f"Column {new} already exists")
        position = min(header.index(name) for name in sources if name in header)
        header = [name for name in header if name not in sources]
        header.insert(position, new)
        for row in rows:
            items = [
                item.strip()
                for name in sources
                for item in (row.pop(name, "") or "").split(";")
                if item.strip()
            ]
            row[new] = ";".join(dict.fromkeys(items))
    ending = "\r\n" if "\r\n" in text else "\n"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator=ending)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def rename_keys(text, renames):
    """Rename top-level JSON keys in place, keeping the file's formatting."""
    data = json.loads(text)
    if not isinstance(data, dict):
        return text
    expected = {renames.get(k, k): v for k, v in data.items()}
    if len(expected) != len(data):
        raise ValueError("Renaming would create a duplicate key")
    for old, new in renames.items():
        if old in data:
            text, count = re.subn(r'"%s"(\s*:)' % re.escape(old), f'"{new}"\\1', text)
            if count != 1:
                raise ValueError(f"Could not locate key {old} exactly once")
    if json.loads(text) != expected:
        raise ValueError("JSON verification failed")
    return text


class Migration:
    """Convert files one at a time, backing each up before replacing it."""

    def __init__(self, renames, merges, apply, backup, bases):
        """Remember the conversion and where backups go."""
        self.renames, self.merges = renames, merges
        self.apply, self.backup, self.bases = apply, backup, bases
        self.files, self.skipped = [], []

    def save_backup(self, path):
        """Copy one file under the backup directory, mirroring its location."""
        root = next(root for root in self.bases if path.is_relative_to(root))
        copy = self.backup / root.name / path.relative_to(root)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copy)

    def text_file(self, path, convert):
        """Convert one text file; replace it only when applying and unchanged meanwhile."""
        if not path.is_file() or path.is_symlink():
            return
        before = path.read_bytes()
        bom = b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b""
        try:
            after = convert(before[len(bom) :].decode("utf-8"))
        except (ValueError, csv.Error) as error:
            self.skipped.append((str(path), str(error)))
            return
        if after.encode() == before[len(bom) :]:
            return
        self.files.append(str(path))
        if not self.apply:
            return
        self.save_backup(path)
        if path.read_bytes() != before:
            self.skipped.append((str(path), "changed while converting"))
            self.files.pop()
            return
        status = path.stat()
        atomic_write(path, bom + after.encode("utf-8"), status.st_mode & 0o777)
        os.chown(path, status.st_uid, status.st_gid)

    def history(self, folder):
        """Rename field keys in one project's ingestion history and re-export its logs."""
        database = folder / "ingestion.sqlite"
        if not database.is_file():
            return
        logs = [database, folder / "ingestion.jsonl", folder / "actions.jsonl"]
        with sqlite3.connect(database) as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(events)")]
            stored = (
                "".join(r[0] or "" for r in db.execute("SELECT fields FROM events"))
                if "fields" in columns
                else ""
            )
            changes = "".join(
                r[0] or "" for r in db.execute("SELECT changes FROM actions")
            )
        old = [
            name
            for name in self.renames
            if name in columns or f'"{name}"' in stored + changes
        ]
        if not old:
            return
        self.files.extend(str(path) for path in logs if path.is_file())
        if not self.apply:
            return
        owners = {p: p.stat() for p in logs if p.is_file()}
        for path in owners:
            self.save_backup(path)
        log = IngestionLog(
            folder, database, lambda: None, log_path=folder / "ingestion.jsonl"
        )
        try:
            with log.db:
                for table, column in (("events", "fields"), ("actions", "changes")):
                    rows = log.db.execute(f"SELECT id, {column} FROM {table}")
                    for id, value in rows.fetchall():
                        data = json.loads(value or "{}")
                        renamed = {self.renames.get(k, k): v for k, v in data.items()}
                        if renamed != data:
                            log.db.execute(
                                f"UPDATE {table} SET {column}=? WHERE id=?",
                                (json.dumps(renamed), id),
                            )
            log.export_log()
            log.export_actions()
        finally:
            log.db.close()
        for path, status in owners.items():
            os.chown(path, status.st_uid, status.st_gid)


def main():
    """Report, and with --apply perform, the field renames."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--projects-root", type=Path)
    parser.add_argument("--rename", action="append", default=[], help="old=new")
    parser.add_argument("--merge", action="append", default=[], help="a,b=new")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, help="Required with --apply")
    args = parser.parse_args()
    if args.apply and (args.backup is None or args.backup.exists()):
        raise SystemExit("--apply needs a new --backup directory")
    renames, merges = pairs(args.rename, "rename"), pairs(args.merge, "merge")
    dataset = args.dataset.resolve()
    projects = args.projects_root and args.projects_root.resolve()
    bases = [p for p in (dataset, projects) if p]
    migration = Migration(renames, merges, args.apply, args.backup, bases)
    plan = lambda text: merge_columns(rename_header(text, renames), merges)
    for folder in sorted(p for p in dataset.iterdir() if p.is_dir()):
        if folder.name in EXCLUDED:
            continue
        for name in INDEXES:
            migration.text_file(folder / name, lambda t: rename_header(t, renames))
        annotations = folder / ANNOTATIONS
        if annotations.is_dir():
            for path in sorted(annotations.glob("*.json")):
                migration.text_file(path, lambda t: rename_keys(t, renames))
    for path in sorted(dataset.glob("*.csv")):
        migration.text_file(path, plan)
    if projects:
        for path in sorted(projects.glob("*/*.csv")):
            migration.text_file(path, plan)
        for folder in sorted(p for p in projects.iterdir() if p.is_dir()):
            migration.history(folder)
    print(
        json.dumps(
            dict(
                mode="applied" if args.apply else "dry run",
                files_changed=len(migration.files),
                skipped=[dict(file=f, reason=r) for f, r in migration.skipped],
            ),
            indent=2,
        )
    )
    return int(bool(migration.skipped))


if __name__ == "__main__":
    raise SystemExit(main())
