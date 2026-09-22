"""Read capture metadata and dashboard definitions from the dataset."""

import ast
import csv
import json
from pathlib import Path

MATRIX_NAME = "internal_colour_print_enhancement_2"
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


def capture_device(row):
    """Classify recognized sensor formats; a device label alone cannot identify an SDK."""
    device = (row.get("capture_device") or "").strip()
    raw = (row.get("input_sensor") or "").strip()
    if raw.lower().startswith("websdk;"):
        return "web", device or "unknown"
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
            model = model.strip()
            return "app", (device or "unknown") if model.lower() == "unknown" else model
    if raw.startswith("model:"):
        model = raw.split(",", 1)[0].removeprefix("model:").strip()
        if model:
            return "app", (device or "unknown") if model.lower() == "unknown" else model
    return "unknown", device or "unknown"


def records(root):
    """Return capture records in batch and CSV order with their original line numbers."""
    root = Path(root).resolve()
    result = []
    for folder in sorted(root.iterdir()):
        path = folder / INDEX_NAME
        if folder.name in EXCLUDED or not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for line, row in enumerate(csv.DictReader(stream), 2):
                sdk, device = capture_device(row)
                annotation = collection_annotation(folder, row.get("uuid", ""))
                result.append(
                    dict(
                        key="/".join(
                            (folder.name, row.get("uuid", ""), row.get("filename", ""))
                        ),
                        folder=folder.name,
                        line=line,
                        sdk=sdk,
                        device=device,
                        annotation_lighting=annotation.get("lighting", ""),
                        metadata=row,
                    )
                )
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
