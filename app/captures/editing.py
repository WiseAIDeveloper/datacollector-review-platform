"""Validated, optimistic edits to both capture indexes."""

import csv
import io
from pathlib import Path

from .catalog import EXCLUDED
from .deletion import INDEXES, SAFE_FOLDER, atomic_write


class Conflict(ValueError):
    """The stored capture or review differs from the user's expected snapshot."""


def validate_changes(changes, allowed_fields, naming=None):
    """Reject columns no field edits and values outside each field's standard names.

    Without `allowed_fields`, every naming-file field column may be edited. A blank
    device column means the App SDK's detected model is used instead.
    """
    columns = naming.editable() if naming else {}
    allowed = set(columns) if allowed_fields is None else allowed_fields
    if not isinstance(changes, dict) or not changes or not set(changes) <= allowed:
        raise ValueError("Invalid metadata fields")
    if any(
        not isinstance(value, str) or len(value) > 4096 for value in changes.values()
    ):
        raise ValueError("Invalid field value")
    for column, value in changes.items():
        field = columns.get(column)
        if field is None or field.accepted is None:
            continue
        if field.role == "identity" and not value.strip():
            raise ValueError(f"{field.key} cannot be empty")
        blank = not value and (field.role == "device" or not field.required)
        if field.accepted and not blank and value not in field.accepted:
            raise ValueError(f"Choose a standard {field.key}")


def prepare_edit(path, folder, uuid, filename, changes, expected):
    """Validate one index and prepare replacement bytes without changing the file."""
    if path.resolve().parent != folder:
        raise ValueError("Invalid index path")
    original = path.read_bytes()
    reader = csv.DictReader(io.StringIO(original.decode("utf-8-sig"), newline=""))
    rows = list(reader)
    fields = list(reader.fieldnames or [])
    matches = [row for row in rows if row.get("uuid") == uuid]
    if len(matches) != 1:
        raise Conflict("Capture changed or is missing; reopen it")
    selected = matches[0]
    primary = path.name == INDEXES[0]
    if (primary or "filename" in fields) and selected.get("filename") != filename:
        raise Conflict("Capture filename changed; reopen it")
    if not primary and "filename" not in fields and selected.get("ori_path"):
        if Path(selected["ori_path"]).name != filename:
            raise Conflict("Capture image path changed; reopen it")
    if primary and selected != expected:
        raise Conflict("Metadata changed since you opened it; reopen it")
    selected.update(changes)
    fields.extend(key for key in changes if key not in fields)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    return path, original, bom + output.getvalue().encode(), path.stat().st_mode & 0o777


def edit_capture(
    root,
    folder_name,
    uuid,
    filename,
    changes,
    expected,
    *,
    allowed_fields=None,
    naming=None,
):
    """Update both indexes, preserving optimistic checks and rolling back failed writes."""
    root = Path(root).resolve()
    if not isinstance(folder_name, str) or not SAFE_FOLDER.fullmatch(folder_name):
        raise ValueError("Invalid folder")
    folder = (root / folder_name).resolve()
    if folder.parent != root or folder_name in EXCLUDED:
        raise ValueError("Invalid folder")
    validate_changes(changes, allowed_fields, naming)
    prepared = [
        prepare_edit(folder / name, folder, uuid, filename, changes, expected)
        for name in INDEXES
    ]
    for path, original, _, _ in prepared:
        if path.read_bytes() != original:
            raise Conflict("Index changed; reopen capture")
    written = []
    try:
        for path, original, replacement, mode in prepared:
            atomic_write(path, replacement, mode)
            written.append((path, original, mode))
    except Exception:
        for path, original, mode in written:
            atomic_write(path, original, mode)
        raise
    return {"updated": True, "changes": changes, "json_preserved": True}
