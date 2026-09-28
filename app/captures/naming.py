"""Standard lighting, device, and identity names shared by every project.

The naming file has one block per field. Each block names the column it is read
from and its accepted values. Device spellings are keyed by the column they are
found in, so a label and a detected model code are never confused.
"""

import json
import logging
import re
import threading
from pathlib import Path

LOGGER = logging.getLogger(__name__)
MAX_BYTES = 1_000_000
SDKS = ("app", "web")
SENSOR_MODEL = "input_sensor.model"
COLUMN = re.compile(r"input_sensor\.model|annotation\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]+")


def names(value, label, allow_empty=False):
    """Validate a list of unique, nonempty, trimmed strings."""
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"Naming file: {label} must be a nonempty list")
    if any(not isinstance(v, str) or not v or v != v.strip() for v in value):
        raise ValueError(f"Naming file: {label} must contain trimmed, nonempty text")
    if len(value) != len(set(value)):
        raise ValueError(f"Naming file: {label} contains duplicates")
    return value


def keys(value, required, optional, label):
    """Require an object with exactly the required keys plus any optional ones."""
    if not isinstance(value, dict) or not required <= set(value) <= required | optional:
        expected = ", ".join(sorted(required | optional))
        raise ValueError(f"Naming file: {label} must be an object with {expected}")
    return value


def description(block, label):
    """Validate an optional free-text description."""
    text = block.get("description", "")
    if not isinstance(text, str) or len(text) > 1000:
        raise ValueError(
            f"Naming file: {label}.description must be text up to 1000 characters"
        )
    return text


def column_name(value, label):
    """Validate a column: a CSV column, the sensor model, or annotation.<key>."""
    if not isinstance(value, str) or not COLUMN.fullmatch(value):
        raise ValueError(
            f"Naming file: {label} must be one CSV column, "
            f"{SENSOR_MODEL} or annotation.<key>"
        )
    return value


def columns(block, label):
    """Validate a column and its optional fallback; return them in reading order."""
    column = column_name(block.get("column"), f"{label}.column")
    if "fallback" not in block:
        return (column,)
    fallback = column_name(block["fallback"], f"{label}.fallback")
    if fallback == column:
        raise ValueError(f"Naming file: {label}.fallback repeats column")
    return column, fallback


def read_column(column, row, annotation, sensor_model):
    """Read one column as trimmed text; an Unknown sensor model counts as empty."""
    if column == SENSOR_MODEL:
        value = sensor_model
    elif column.startswith("annotation."):
        value = annotation.get(column.removeprefix("annotation."), "")
    else:
        value = row.get(column, "")
    value = value.strip() if isinstance(value, str) else ""
    return "" if column == SENSOR_MODEL and value.lower() == "unknown" else value


def read_first(order, row, annotation, sensor_model):
    """Return the first column with a value, or the main column when all are empty."""
    for column in order:
        if value := read_column(column, row, annotation, sensor_model):
            return column, value
    return order[0], ""


class Naming:
    """A validated naming document: columns, accepted values, and device spellings."""

    def __init__(self, document):
        """Reject unknown keys, duplicates, and spellings that could mean two devices."""
        keys(document, {"lighting", "identity", "device"}, set(), "the file")
        optional = {"description", "fallback"}
        self.columns, self.descriptions = {}, {}
        for field, allow_empty in (("lighting", False), ("identity", True)):
            block = keys(document[field], {"column", "accepted"}, optional, field)
            self.columns[field] = columns(block, field)
            self.descriptions[field] = description(block, field)
            accepted = names(block["accepted"], f"{field}.accepted", allow_empty)
            setattr(self, "identities" if field == "identity" else field, set(accepted))
        block = keys(
            document["device"], {"app", "web", "accepted"}, {"description"}, "device"
        )
        self.descriptions["device"] = description(block, "device")
        for sdk in SDKS:
            sdk_block = keys(block[sdk], {"column"}, {"fallback"}, f"device.{sdk}")
            self.columns[f"{sdk}_device"] = columns(sdk_block, f"device.{sdk}")
        read = {c for sdk in SDKS for c in self.columns[f"{sdk}_device"]}
        accepted = block["accepted"]
        if not isinstance(accepted, dict) or not accepted:
            raise ValueError("Naming file: device.accepted must be a nonempty object")
        self.devices = set(accepted)
        self.aliases = {column: {} for column in read}
        for device, spellings in accepted.items():
            names([device], "device names")
            label = f"device.accepted.{device}"
            if not isinstance(spellings, dict) or not set(spellings) <= read:
                raise ValueError(
                    f"Naming file: {label} may only list columns device.app/web read: "
                    + ", ".join(sorted(read))
                )
            for column, values in spellings.items():
                for raw in names(values, f"{label}.{column}", allow_empty=True):
                    if raw in self.devices:
                        raise ValueError(
                            f"Naming file: {raw} is already a standard device name"
                        )
                    if raw in self.aliases[column]:
                        raise ValueError(
                            f"Naming file: {column} value {raw} maps to two devices"
                        )
                    self.aliases[column][raw] = device

    def device(self, column, raw):
        """Return the standard device for a value read from a column, or None."""
        if raw in self.devices:
            return raw
        return self.aliases.get(column, {}).get(raw)

    def standardize(self, sdk, row, annotation, sensor_model):
        """Report each field's standard value, raw value, source column, and issue."""
        result = {}
        for field, accepted in (
            ("lighting", self.lighting),
            ("identity", self.identities),
        ):
            column, raw = read_first(self.columns[field], row, annotation, sensor_model)
            issue = ""
            if not raw:
                issue = f"Missing {field} ({column})"
            elif accepted and raw not in accepted:
                issue = f"{raw} is not an accepted {field}"
            result[field] = dict(value=raw, raw=raw, source=column, issue=issue)
        result["device"] = self.standardize_device(sdk, row, annotation, sensor_model)
        return result

    def standardize_device(self, sdk, row, annotation, sensor_model):
        """Map the SDK's device column (or its fallback) to a standard device name."""
        if sdk not in SDKS:
            return dict(value="", raw="", source="", issue="SDK not recognized")
        column, raw = read_first(
            self.columns[f"{sdk}_device"], row, annotation, sensor_model
        )
        if not raw:
            return dict(
                value="", raw="", source=column, issue=f"Missing device ({column})"
            )
        standard = self.device(column, raw)
        if standard is None:
            issue = f"{raw} ({column}) is not an accepted device"
            return dict(value=raw, raw=raw, source=column, issue=issue)
        return dict(value=standard, raw=raw, source=column, issue="")


def load(path):
    """Parse and validate one naming file."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Naming file must be at most 1 MB")
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Naming file is not valid JSON: {error}") from error
    return Naming(document)


class NamingFile:
    """Reload the naming file when it changes, keeping the last valid version."""

    def __init__(self, path):
        """Require a valid file at startup so a broken file cannot go unnoticed."""
        self.path = Path(path)
        self.lock = threading.Lock()
        self.stamp = self.signature()
        self.naming = load(self.path)
        self.error = ""

    def signature(self):
        """Identify the file version by modification time and size."""
        stat = self.path.stat()
        return stat.st_mtime_ns, stat.st_size

    def current(self):
        """Return the newest valid naming document; report reload failures via error."""
        with self.lock:
            try:
                stamp = self.signature()
                if stamp != self.stamp:
                    self.stamp = stamp
                    self.naming = load(self.path)
                    self.error = ""
            except (OSError, ValueError) as error:
                self.error = (
                    f"Naming file not reloaded, using last valid version: {error}"
                )
                LOGGER.error("Naming file reload failed (%s)", type(error).__name__)
            return self.naming
