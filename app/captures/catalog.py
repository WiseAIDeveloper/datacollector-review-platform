"""Read capture metadata and dashboard definitions from the dataset."""

import ast
import csv
import json
import threading
from pathlib import Path

MATRIX_NAME = "001_MyKad_ColourPrintEnhancement2"
INDEX_NAME = "index_annotation_.csv"
EXCLUDED = {"test", "webcam_genuine", "webcam_replay", "capture_viewer"}


def annotation_path(folder, uuid):
    """Locate a capture's collection annotation JSON within its dataset folder."""
    return folder / "mykadfront/datacollector_annotation" / (uuid + ".json")


def collection_annotation(folder, uuid):
    """Read collection metadata, treating missing or malformed JSON as empty."""
    path = annotation_path(folder, uuid)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def sensor_model(row):
    """Classify the SDK from input_sensor and return the native model text, if any."""
    raw = (row.get("input_sensor") or "").strip()
    if raw.lower().startswith("websdk;"):
        return "web", ""
    try:
        sensor = json.loads(raw)
    except (ValueError, TypeError):
        try:
            sensor = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            sensor = None
    if isinstance(sensor, dict):
        model = sensor.get("model")
        if isinstance(model, str) and model.strip():
            return "app", model.strip()
    if raw.startswith("model:"):
        model = raw.split(",", 1)[0].removeprefix("model:").strip()
        if model:
            return "app", model
    return "unknown", ""


def capture_fields(naming, row, annotation):
    """Classify the SDK and standardize every naming-file field of one capture row."""
    sdk, model = sensor_model(row)
    fields = naming.standardize(sdk, row, annotation, model)
    device = fields[naming.device.key]
    if sdk == "unknown":
        # Without a recognized sensor, show the web label as the device, unchanged.
        label = naming.device.standardize("web", row, annotation, model)["raw"]
        device = dict(device, value=label or "unknown")
    elif not device["value"]:
        known = model if model.lower() != "unknown" else ""
        device = dict(device, value=device["raw"] or known or "unknown")
    return sdk, dict(fields, **{naming.device.key: device})


def records(root, naming):
    """Return capture records in batch and CSV order with their original line numbers.

    Each record has every naming-file field by name (`fields`, standard values),
    the same fields as written in the collection annotation (`annotation`), and
    each field's raw value, source column, and any issue (`naming`).
    """
    root = Path(root).resolve()
    result = []
    for folder in sorted(root.iterdir()):
        path = folder / INDEX_NAME
        if folder.name in EXCLUDED or not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for line, row in enumerate(csv.DictReader(stream), 2):
                result.append(capture_record(folder, line, row, naming))
    return result


def capture_record(folder, line, row, naming):
    """Build one capture's standard fields and metadata without changing its CSV row."""
    annotation = collection_annotation(folder, row.get("uuid", ""))
    sdk, standard = capture_fields(naming, row, annotation)
    values = {key: value["value"] for key, value in standard.items()}
    return dict(
        key="/".join((folder.name, row.get("uuid", ""), row.get("filename", ""))),
        folder=folder.name,
        line=line,
        sdk=sdk,
        device=values[naming.device.key],
        identity=values[naming.identity.key],
        fields=values,
        annotation={
            field.key: str(annotation.get(field.edit_column, ""))
            for field in naming.fields
            if field.edit_column
        },
        naming=standard,
        metadata=row,
    )


def file_stamp(path):
    """Detect content changes and atomic replacements without reading file contents."""
    try:
        stat = path.stat()
        return (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )
    except OSError:
        return None


class CatalogCache:
    """Reuse unchanged captures while checking CSV, annotation, and naming changes on every read."""

    def __init__(self, root):
        """Keep one thread-safe cache per dataset, shared between project readers."""
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.indexes = {}
        self.entries = {}
        self.generation = 0
        self.snapshot = []
        self.naming = None

    def records(self, naming):
        """Return current records in CSV order, rebuilding only changed metadata.

        Returned records are read-only to callers. New cache dictionaries replace old
        ones so concurrent serializers retain a consistent snapshot. Deleted files
        and rows are discarded; no time-based staleness is introduced.
        """
        generation = self.generation
        with self.lock:
            # A simultaneous caller already checked files after this read began.
            if self.generation != generation and self.naming is naming:
                return self.snapshot
            indexes, entries, result = {}, {}, []
            for folder in sorted(self.root.iterdir()):
                path = folder / INDEX_NAME
                if folder.name in EXCLUDED or not path.is_file():
                    continue
                stamp = file_stamp(path)
                previous = self.indexes.get(folder.name)
                if stamp is not None and previous and previous[0] == stamp:
                    rows = previous[1]
                else:
                    with path.open(newline="", encoding="utf-8-sig") as stream:
                        rows = list(csv.DictReader(stream))
                # Do not cache a CSV that changed while it was being read.
                if stamp is not None and file_stamp(path) == stamp:
                    indexes[folder.name] = stamp, rows
                for line, row in enumerate(rows, 2):
                    identity = folder.name, line
                    annotation = annotation_path(folder, row.get("uuid", ""))
                    annotation_stamp = file_stamp(annotation)
                    previous = self.entries.get(identity)
                    if (
                        previous
                        and previous[0] is naming
                        and previous[1] == annotation_stamp
                        and previous[2]["metadata"] == row
                    ):
                        record = previous[2]
                        entries[identity] = previous
                    else:
                        record = capture_record(folder, line, row, naming)
                        if file_stamp(annotation) == annotation_stamp:
                            entries[identity] = naming, annotation_stamp, record
                    result.append(record)
            self.indexes, self.entries = indexes, entries
            self.snapshot, self.naming = result, naming
            self.generation += 1
            return result


def matrix(root):
    """Read only matrix rows belonging to the platform's configured test plan."""
    root = Path(root)
    with (root / f"{MATRIX_NAME}.csv").open(newline="", encoding="utf-8-sig") as stream:
        return [
            row
            for row in csv.DictReader(stream)
            if row.get("matrix_name") == MATRIX_NAME
        ]


def batches(root):
    """Read batch definitions used for coverage and metadata choices."""
    root = Path(root)
    with (root / f"{MATRIX_NAME}_batches.csv").open(
        newline="", encoding="utf-8-sig"
    ) as stream:
        return list(csv.DictReader(stream))
