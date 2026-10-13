"""Move captures between configured batches with checked writes and rollback."""

import csv
import io
import json
import shutil
from pathlib import Path

from .catalog import EXCLUDED, annotation_path
from .deletion import INDEXES, SAFE_FOLDER, atomic_write, capture_images, remove_row
from .editing import Conflict, prepare_edit, validate_changes


def append_row(before, row):
    """Append a capture, retaining existing CSV bytes when its schema permits."""
    text = (before or b"").decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = list(reader.fieldnames or [])
    rows = list(reader)
    if any(item.get("uuid") == row["uuid"] for item in rows):
        raise Conflict("Destination already contains this capture")
    extra = [key for key in row if key not in fields]
    output = io.StringIO(newline="")
    newline = "\r\n" if "\r\n" in text or not text else "\n"
    writer = csv.DictWriter(output, fieldnames=fields + extra, lineterminator=newline)
    if not fields or extra:
        writer.writeheader()
        writer.writerows(rows)
        prefix = (
            b"\xef\xbb\xbf" if before and before.startswith(b"\xef\xbb\xbf") else b""
        )
    else:
        prefix = before + (
            newline.encode() if text and not text.endswith(("\n", "\r")) else b""
        )
    writer.writerow(row)
    return prefix + output.getvalue().encode()


def checked_path(path, root):
    """Reject symlinks and paths escaping the dataset, including missing targets."""
    if not path.resolve().is_relative_to(root):
        raise ValueError("Capture path leaves the dataset")
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Capture paths must not contain symlinks")
    return path


def move_capture(
    root,
    folder_name,
    uuid,
    filename,
    destination,
    changes,
    expected,
    *,
    batches,
    naming,
    quality_path
):
    """Move indexes, images, annotation and quality key; restore originals on failure."""
    root = Path(root).resolve()
    for name in (folder_name, destination):
        if (
            not isinstance(name, str)
            or not SAFE_FOLDER.fullmatch(name)
            or name in EXCLUDED
        ):
            raise ValueError("Invalid batch folder")
    if folder_name == destination:
        raise ValueError("Choose a different batch")
    if (
        not isinstance(uuid, str)
        or Path(uuid).name != uuid
        or uuid in {"", ".", ".."}
        or Path(filename).name != filename
    ):
        raise ValueError("Invalid capture identifier")
    source = checked_path(root / folder_name, root)
    target = checked_path(root / destination, root)
    plan = expected.get("test_plan_name") if isinstance(expected, dict) else None
    pairs = {(b["batch_name"], b["test_plan_name"]) for b in batches}
    if (folder_name, plan) not in pairs or (destination, plan) not in pairs:
        raise ValueError("Choose a batch in the same project and test plan")
    if changes:
        validate_changes(changes, None, naming)
    elif not isinstance(changes, dict):
        raise ValueError("Invalid metadata fields")
    prepared = []
    source_rows = []
    for name in INDEXES:
        src = checked_path(source / name, root)
        # Reuse optimistic metadata, filename and secondary-image checks.
        prepare_edit(src, source, uuid, filename, {}, expected)
        before, after, row = remove_row(
            src, uuid, filename if name == INDEXES[0] else None
        )
        source_rows.append(dict(row))
        if name == INDEXES[0] and row != expected:
            raise Conflict("Metadata changed since you opened it; reopen it")
        row.update(changes)
        for field in ("batch", "batch_name"):
            if field in row:
                row[field] = destination
        row["batch" if name == INDEXES[0] else "batch_name"] = destination
        dst = checked_path(target / name, root)
        previous = dst.read_bytes() if dst.exists() else None
        prepared.extend(
            [
                (src, before, after, src.stat().st_mode & 0o777),
                (
                    dst,
                    previous,
                    append_row(previous, row),
                    dst.stat().st_mode & 0o777 if dst.exists() else 0o644,
                ),
            ]
        )
    for directory in (source / "mykadfront/orig", source / "mykadfront/crop"):
        checked_path(directory, root)
    files = set()
    for row in source_rows:
        for field in ("ori_path", "ocr_path"):
            if row.get(field):
                checked_path(source / row[field], root)
        files.update(capture_images(source, uuid, row))
        for row_path in ("ori_path", "ocr_path"):
            if row.get(row_path) and not (source / row[row_path]).is_file():
                raise Conflict("A referenced capture image is missing")
    if not files or not any(path.is_file() for path in files):
        raise Conflict("Capture images are missing")
    annotation = checked_path(annotation_path(source, uuid), root)
    if annotation.exists():
        files.add(annotation)
    moves = []
    for src in sorted(files):
        checked_path(src, root)
        dst = checked_path(target / src.relative_to(source), root)
        if dst.exists():
            raise Conflict("Destination already contains a capture file")
        if not src.is_file():
            raise Conflict("A capture file is missing")
        moves.append((src, dst))
    old_key = "/".join((folder_name, uuid, filename))
    new_key = "/".join((destination, uuid, filename))
    quality_path = Path(quality_path)
    if quality_path.exists():
        before = quality_path.read_bytes()
        reviews = json.loads(before)
        if new_key in reviews:
            raise Conflict("Destination already contains a quality review")
        if old_key in reviews:
            entry = reviews.pop(old_key)
            reviews[new_key] = dict(entry, key=new_key, folder=destination)
            prepared.append(
                (
                    quality_path,
                    before,
                    (json.dumps(reviews, indent=2, ensure_ascii=False) + "\n").encode(),
                    quality_path.stat().st_mode & 0o777,
                )
            )
    for path, before, _, _ in prepared:
        if (path.read_bytes() if path.exists() else None) != before:
            raise Conflict("Capture indexes changed; reopen capture")
    created_dirs, copied, written, removed = [], [], [], []
    try:
        for path in [item[0] for item in prepared] + [dst for _, dst in moves]:
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory)
        for src, dst in moves:
            # Exclusive creation prevents overwriting an arriving collector file.
            with src.open("rb") as stream, dst.open("xb") as output:
                copied.append(dst)
                shutil.copyfileobj(stream, output)
            shutil.copystat(src, dst)
        for path, before, after, mode in prepared:
            if (path.read_bytes() if path.exists() else None) != before:
                raise Conflict("Capture indexes changed; reopen capture")
            atomic_write(path, after, mode)
            written.append((path, before, mode))
        for src, dst in moves:
            src.unlink()
            removed.append((src, dst))
    except Exception:
        for src, dst in removed:
            shutil.copy2(dst, src)
        for path, before, mode in reversed(written):
            if before is None:
                path.unlink()
            else:
                atomic_write(path, before, mode)
        for dst in copied:
            dst.unlink()
        for directory in reversed(created_dirs):
            directory.rmdir()
        raise
    return dict(
        updated=True,
        moved=True,
        folder=destination,
        key=new_key,
        changes=changes,
        json_preserved=True,
    )
