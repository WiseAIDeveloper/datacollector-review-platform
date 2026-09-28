"""Rewrite old lighting and device values to standard names, with backups.

Runs as a dry run unless --apply is given. Only the named cells change: other
CSV rows keep their exact bytes, and JSON files keep their formatting. Each file
is backed up before it is replaced and skipped if it changed while being read.
"""

import argparse
import csv
import io
import json
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
# Capture files: column/key -> field kind. Plan files add semicolon lists.
CAPTURE_FIELDS = {"lighting": "lighting", "capture_device": "device"}
PLAN_FIELDS = {"lighting": "lighting", "device": "device"}
PLAN_LISTS = {
    "expected_lighting": "lighting",
    "expected_web_devices": "device",
    "expected_app_devices": "device",
}


def parse_mapping(pairs):
    """Turn repeated old=new arguments into a dictionary."""
    mapping = {}
    for pair in pairs:
        old, separator, new = pair.partition("=")
        if not separator or not old or not new or old in mapping:
            raise SystemExit(f"Invalid or repeated mapping: {pair}")
        mapping[old] = new
    return mapping


def device_mapping(naming):
    """Map every listed device spelling, in any column, to its standard name."""
    mapping = {}
    for spellings in naming.aliases.values():
        for raw, device in spellings.items():
            if mapping.setdefault(raw, device) != device:
                raise SystemExit(f"Device spelling {raw} is ambiguous across columns")
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


def convert_json(text, changes, mappings):
    """Replace mapped top-level string values in place, keeping the formatting."""
    data = json.loads(text)
    if not isinstance(data, dict):
        return text
    expected = dict(data)
    for key, kind in CAPTURE_FIELDS.items():
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


def process(path, kind, changes, mappings, apply, backup, base):
    """Convert one file; back it up and replace it only when applying."""
    if not path.is_file() or path.is_symlink():
        return
    before = path.read_bytes()
    bom = b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b""
    text = before[len(bom) :].decode("utf-8")
    if kind == "json":
        try:
            after = convert_json(text, changes, mappings)
        except json.JSONDecodeError:
            changes.skipped.append((str(path), "invalid JSON"))
            return
    elif kind == "capture_csv":
        after = convert_csv(text, CAPTURE_FIELDS, {}, changes, mappings)
    else:
        after = convert_csv(text, PLAN_FIELDS, PLAN_LISTS, changes, mappings)
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
    atomic_write(path, bom + after.encode("utf-8"), path.stat().st_mode & 0o777)


def main():
    """Report, and with --apply perform, lighting and device normalization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--projects-root", type=Path)
    parser.add_argument("--naming", required=True, type=Path)
    parser.add_argument(
        "--lighting", action="append", default=[], help="old=new, repeatable"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, help="Required with --apply")
    args = parser.parse_args()
    if args.apply and (args.backup is None or args.backup.exists()):
        raise SystemExit("--apply needs a new --backup directory")
    naming = load(args.naming)
    lighting = parse_mapping(args.lighting)
    if not set(lighting.values()) <= naming.lighting:
        raise SystemExit("Every new lighting value must be accepted in the naming file")
    mappings = {
        "lighting": lighting,
        "device": device_mapping(naming),
        "accepted": {"lighting": naming.lighting, "device": naming.devices},
    }
    base = [p.resolve() for p in (args.dataset, args.projects_root) if p]
    changes = Changes()
    for path, kind in targets(
        args.dataset.resolve(), args.projects_root and args.projects_root.resolve()
    ):
        process(path, kind, changes, mappings, args.apply, args.backup, base)
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
