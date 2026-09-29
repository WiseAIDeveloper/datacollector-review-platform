"""Rewrite old field values to their standard names, with backups.

Each naming-file field is converted wherever it is stored: the index columns and
annotation keys it is read from, the matrix column named after it, and its
`expected_<field>` batch list. Listed spellings map automatically; other old
values are mapped with --map field:old=new.

Runs as a dry run unless --apply is given. Only the named cells change: other
CSV rows keep their exact bytes, and JSON files keep their formatting. Each file
is backed up before it is replaced and skipped if it changed while being read.
"""

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.captures.catalog import EXCLUDED
from app.captures.deletion import atomic_write
from app.captures.naming import load

INDEXES = ("index_annotation_.csv", "index_annotation_mykadfront.csv")
ANNOTATIONS = "mykadfront/datacollector_annotation"


def layout(naming):
    """Map capture columns, plan columns, and batch lists to the field they hold."""
    checked = [field for field in naming.fields if field.accepted]
    capture = {
        column: field.key
        for field in checked
        for order in getattr(field, "sdk_columns", {"": field.columns}).values()
        for column in order
        if "." not in column
    }
    plan = {field.key: field.key for field in checked}
    lists = {f"expected_{field.key}": field.key for field in checked}
    return capture, plan, lists


def parse_mappings(pairs, naming):
    """Turn repeated field:old=new arguments into per-field dictionaries."""
    mappings = {}
    for pair in pairs:
        key, colon, rest = pair.partition(":")
        old, separator, new = rest.partition("=")
        field = naming.field(key)
        if not colon or not separator or not old or field is None:
            raise SystemExit(f"Invalid mapping (use field:old=new): {pair}")
        if old in mappings.setdefault(key, {}) or new not in (field.accepted or {new}):
            raise SystemExit(f"Repeated mapping or unaccepted new value: {pair}")
        mappings[key][old] = new
    return mappings


def spellings(field):
    """Map every listed spelling of a field, in any column, to its standard name."""
    if field.role != "device":
        return dict(field.aliases)
    mapping = {}
    for aliases in field.aliases.values():
        for raw, standard in aliases.items():
            if mapping.setdefault(raw, standard) != standard:
                raise SystemExit(f"{field.key} spelling {raw} is ambiguous")
    return mapping


class Changes:
    """Collect per-value counts and per-file outcomes for the report."""

    def __init__(self):
        """Start with no recorded changes."""
        self.values = Counter()
        self.unmapped = Counter()
        self.files = []
        self.skipped = []

    def convert(self, kind, value, mappings):
        """Return the standard value, recording what changed or stayed unknown."""
        new = mappings[kind].get(value.strip(), value)
        if new != value:
            self.values[(kind, value, new)] += 1
        elif value.strip() and value not in mappings["accepted"][kind]:
            self.unmapped[(kind, value)] += 1
        return new


def convert_csv(text, fields, lists, changes, mappings):
    """Return CSV text with mapped cells; unchanged rows keep their exact text."""
    lines = text.splitlines(keepends=True)
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        return text
    columns = {
        i: (name, kind)
        for i, name in enumerate(header)
        for kind in [fields.get(name) or lists.get(name)]
        if kind
    }
    start, output, expected = reader.line_num, lines[: reader.line_num], [header]
    for row in reader:
        end = reader.line_num
        new = list(row)
        for i, (name, kind) in columns.items():
            if i >= len(row):
                continue
            if name in lists:
                items = row[i].split(";")
                new[i] = ";".join(
                    changes.convert(kind, item, mappings) for item in items
                )
            else:
                new[i] = changes.convert(kind, row[i], mappings)
        original = "".join(lines[start:end])
        if new == row:
            output.append(original)
        else:
            ending = "\r\n" if original.endswith("\r\n") else "\n"
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator=ending).writerow(new)
            output.append(buffer.getvalue())
        expected.append(new)
        start = end
    result = "".join(output)
    if list(csv.reader(io.StringIO(result, newline=""))) != expected:
        raise ValueError("CSV verification failed")
    return result


def convert_json(text, fields, changes, mappings):
    """Replace mapped top-level string values in place, keeping the formatting."""
    data = json.loads(text)
    if not isinstance(data, dict):
        return text
    expected = dict(data)
    for key, kind in fields.items():
        if isinstance(data.get(key), str):
            new = changes.convert(kind, data[key], mappings)
            if new == data[key]:
                continue
            pattern = re.compile(
                r'("%s"\s*:\s*)%s' % (key, re.escape(json.dumps(data[key])))
            )
            text, count = pattern.subn(lambda m: m.group(1) + json.dumps(new), text)
            if count != 1:
                raise ValueError(f"Could not locate {key} exactly once")
            expected[key] = new
    if json.loads(text) != expected:
        raise ValueError("JSON verification failed")
    return text


def targets(dataset, projects):
    """List every file to check, with the converter that applies to it."""
    # Folders the review platform ignores (test and webcam data) are left alone.
    folders = (p for p in dataset.iterdir() if p.is_dir() and p.name not in EXCLUDED)
    for folder in sorted(folders):
        for name in INDEXES:
            yield folder / name, "capture_csv"
        annotations = folder / ANNOTATIONS
        if annotations.is_dir():
            for path in sorted(annotations.glob("*.json")):
                yield path, "json"
    if projects:
        for path in sorted(projects.glob("*/*.csv")):
            yield path, "plan_csv"


def process(path, kind, layout, changes, mappings, apply, backup, base):
    """Convert one file; back it up and replace it only when applying."""
    if not path.is_file() or path.is_symlink():
        return
    before = path.read_bytes()
    bom = b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b""
    text = before[len(bom) :].decode("utf-8")
    capture, plan, lists = layout
    if kind == "json":
        try:
            after = convert_json(text, capture, changes, mappings)
        except json.JSONDecodeError:
            changes.skipped.append((str(path), "invalid JSON"))
            return
    elif kind == "capture_csv":
        after = convert_csv(text, capture, {}, changes, mappings)
    else:
        after = convert_csv(text, plan, lists, changes, mappings)
    if after == text:
        return
    changes.files.append(str(path))
    if not apply:
        return
    root, relative = next(
        (root, path.relative_to(root)) for root in base if path.is_relative_to(root)
    )
    copy = backup / root.name / relative
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(before)
    shutil.copystat(path, copy)
    if path.read_bytes() != before:
        changes.skipped.append((str(path), "changed while converting"))
        changes.files.pop()
        return
    status = path.stat()
    atomic_write(path, bom + after.encode("utf-8"), status.st_mode & 0o777)
    # The replacement is a new file; give it the original owner and group back.
    os.chown(path, status.st_uid, status.st_gid)


def main():
    """Report, and with --apply perform, field value normalization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--projects-root", type=Path)
    parser.add_argument("--naming", required=True, type=Path)
    parser.add_argument(
        "--map", action="append", default=[], help="field:old=new, repeatable"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, help="Required with --apply")
    args = parser.parse_args()
    if args.apply and (args.backup is None or args.backup.exists()):
        raise SystemExit("--apply needs a new --backup directory")
    naming = load(args.naming)
    extra = parse_mappings(args.map, naming)
    checked = [field for field in naming.fields if field.accepted]
    mappings = {
        field.key: {**spellings(field), **extra.get(field.key, {})} for field in checked
    }
    mappings["accepted"] = {field.key: field.accepted for field in checked}
    base = [p.resolve() for p in (args.dataset, args.projects_root) if p]
    changes = Changes()
    for path, kind in targets(
        args.dataset.resolve(), args.projects_root and args.projects_root.resolve()
    ):
        process(
            path, kind, layout(naming), changes, mappings, args.apply, args.backup, base
        )
    print(
        json.dumps(
            dict(
                mode="applied" if args.apply else "dry run",
                files_changed=len(changes.files),
                changes=[
                    dict(field=k, old=o, new=n, count=c)
                    for (k, o, n), c in sorted(changes.values.items())
                ],
                unmapped=[
                    dict(field=k, value=v, count=c)
                    for (k, v), c in sorted(changes.unmapped.items())
                ],
                skipped=[dict(file=f, reason=r) for f, r in changes.skipped],
            ),
            indent=2,
        )
    )
    return int(bool(changes.skipped))


if __name__ == "__main__":
    raise SystemExit(main())
