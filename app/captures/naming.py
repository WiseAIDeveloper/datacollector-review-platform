"""Standard lighting, device, and identity names shared by every project."""

import json
import logging
import re
import threading
from pathlib import Path

LOGGER = logging.getLogger(__name__)
MAX_BYTES = 1_000_000
SDKS = ("app", "web")
SENSOR_MODEL = "input_sensor.model"
SOURCE_FIELDS = ("lighting", "identity", "app_device", "web_device")
SOURCE = re.compile(r"input_sensor\.model|annotation\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]+")


def names(value, label, allow_empty=False):
    """Validate a list of unique, nonempty, trimmed strings."""
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"Naming file: {label} must be a nonempty list")
    if any(not isinstance(v, str) or not v or v != v.strip() for v in value):
        raise ValueError(f"Naming file: {label} must contain trimmed, nonempty text")
    if len(value) != len(set(value)):
        raise ValueError(f"Naming file: {label} contains duplicates")
    return value


def field_name(value, label):
    """Validate one field name: a CSV column, the sensor model, or an annotation key."""
    if not isinstance(value, str) or not SOURCE.fullmatch(value):
        raise ValueError(
            f"Naming file: {label} must be one CSV column, "
            f"{SENSOR_MODEL} or annotation.<key>"
        )
    return value


def source(value, label):
    """Validate one source: its field, an optional fallback field, and a description."""
    if not isinstance(value, dict) or not {"field"} <= set(value) <= {
        "field",
        "fallback",
        "description",
    }:
        raise ValueError(
            f"Naming file: sources.{label} needs a field, "
            "with optional fallback and description"
        )
    field = field_name(value["field"], f"sources.{label}.field")
    fallback = value.get("fallback")
    if fallback is not None:
        fallback = field_name(fallback, f"sources.{label}.fallback")
        if fallback == field:
            raise ValueError(f"Naming file: sources.{label}.fallback repeats field")
    text = value.get("description", "")
    if not isinstance(text, str) or len(text) > 1000:
        raise ValueError(
            f"Naming file: sources.{label}.description must be text up to 1000 characters"
        )
    return field, fallback, text


def read_source(source, row, annotation, sensor_model):
    """Read one configured source as trimmed text; an Unknown sensor model is empty."""
    if source == SENSOR_MODEL:
        value = sensor_model
    elif source.startswith("annotation."):
        value = annotation.get(source.removeprefix("annotation."), "")
    else:
        value = row.get(source, "")
    value = value.strip() if isinstance(value, str) else ""
    return "" if source == SENSOR_MODEL and value.lower() == "unknown" else value


class Naming:
    """A validated naming document: allowed names, device aliases, and field sources."""

    def __init__(self, document):
        """Reject unknown keys, duplicates, and aliases that could mean two devices."""
        if not isinstance(document, dict):
            raise ValueError("Naming file must contain a JSON object")
        unknown = set(document) - {"lighting", "devices", "identities", "sources"}
        if unknown:
            raise ValueError(f"Naming file: unknown keys {', '.join(sorted(unknown))}")
        self.lighting = set(names(document.get("lighting"), "lighting"))
        self.identities = set(
            names(document.get("identities", []), "identities", allow_empty=True)
        )
        devices = document.get("devices")
        if not isinstance(devices, dict) or not devices:
            raise ValueError("Naming file: devices must be a nonempty object")
        self.devices = set(devices)
        self.aliases = {sdk: {} for sdk in SDKS}
        for device, entry in devices.items():
            names([device], "device names")
            if not isinstance(entry, dict) or not set(entry) <= set(SDKS):
                raise ValueError(f"Naming file: devices.{device} may only have app/web")
            for sdk in SDKS:
                raw_values = entry.get(sdk, [])
                for raw in names(raw_values, f"devices.{device}.{sdk}", True):
                    if raw in self.devices:
                        raise ValueError(f"Naming file: alias {raw} is a device name")
                    if raw in self.aliases[sdk]:
                        raise ValueError(
                            f"Naming file: {sdk} alias {raw} maps to two devices"
                        )
                    self.aliases[sdk][raw] = device
        configured = document.get("sources")
        if not isinstance(configured, dict) or set(configured) != set(SOURCE_FIELDS):
            raise ValueError(
                "Naming file: sources needs exactly "
                + ", ".join(SOURCE_FIELDS)
                + " (one field each)"
            )
        parsed = {key: source(configured[key], key) for key in SOURCE_FIELDS}
        self.sources = {key: field for key, (field, _, _) in parsed.items()}
        self.fallbacks = {key: fallback for key, (_, fallback, _) in parsed.items()}
        self.source_descriptions = {key: text for key, (_, _, text) in parsed.items()}

    def read(self, key, row, annotation, sensor_model):
        """Read a source's field, or its fallback when the field is empty.

        Returns the field actually used (the main field when both are empty).
        """
        for column in (self.sources[key], self.fallbacks[key]):
            if column and (value := read_source(column, row, annotation, sensor_model)):
                return column, value
        return self.sources[key], ""

    def device(self, sdk, raw):
        """Return the standard device for a raw value, or None when it is not listed."""
        if raw in self.devices:
            return raw
        return self.aliases.get(sdk, {}).get(raw)

    def standardize(self, sdk, row, annotation, sensor_model):
        """Report each field's standard value, raw value, source column, and issue."""
        result = {}
        for field, allowed in (
            ("lighting", self.lighting),
            ("identity", self.identities),
        ):
            column, raw = self.read(field, row, annotation, sensor_model)
            issue = ""
            if not raw:
                issue = f"Missing {field} ({column})"
            elif allowed and raw not in allowed:
                issue = f"{raw} is not a standard {field} name"
            result[field] = dict(value=raw, raw=raw, source=column, issue=issue)
        result["device"] = self.standardize_device(sdk, row, annotation, sensor_model)
        return result

    def standardize_device(self, sdk, row, annotation, sensor_model):
        """Map the SDK's device field (or its fallback) to a standard device name."""
        if sdk not in SDKS:
            return dict(value="", raw="", source="", issue="SDK not recognized")
        column, raw = self.read(f"{sdk}_device", row, annotation, sensor_model)
        if not raw:
            return dict(
                value="", raw="", source=column, issue=f"Missing device ({column})"
            )
        standard = self.device(sdk, raw)
        if standard is None:
            issue = f"{raw} ({column}) is not mapped to a standard device"
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
