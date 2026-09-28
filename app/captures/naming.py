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
DEFAULT_SOURCES = {
    "lighting": ["lighting"],
    "identity": ["subject"],
    "device": {"app": [SENSOR_MODEL, "capture_device"], "web": ["capture_device"]},
}
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


def sources(value, label):
    """Validate an ordered list of columns a field may be read from."""
    names(value, f"sources.{label}")
    if any(not SOURCE.fullmatch(source) for source in value):
        raise ValueError(
            f"Naming file: sources.{label} must name CSV columns, "
            f"{SENSOR_MODEL} or annotation.<key>"
        )
    return value


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
            for sdk, raw_values in entry.items():
                for raw in names(raw_values, f"devices.{device}.{sdk}", True):
                    if raw in self.devices:
                        raise ValueError(f"Naming file: alias {raw} is a device name")
                    if raw in self.aliases[sdk]:
                        raise ValueError(
                            f"Naming file: {sdk} alias {raw} maps to two devices"
                        )
                    self.aliases[sdk][raw] = device
        configured = document.get("sources", {})
        if not isinstance(configured, dict) or not set(configured) <= set(
            DEFAULT_SOURCES
        ):
            raise ValueError("Naming file: sources may set lighting, identity, device")
        self.sources = {
            "lighting": sources(configured.get("lighting", ["lighting"]), "lighting"),
            "identity": sources(configured.get("identity", ["subject"]), "identity"),
        }
        device_sources = configured.get("device", DEFAULT_SOURCES["device"])
        if not isinstance(device_sources, dict) or set(device_sources) != set(SDKS):
            raise ValueError("Naming file: sources.device needs app and web lists")
        self.sources["device"] = {
            sdk: sources(device_sources[sdk], f"device.{sdk}") for sdk in SDKS
        }

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
            source, raw = first_value(
                self.sources[field], row, annotation, sensor_model
            )
            issue = ""
            if not raw:
                issue = f"Missing {field}"
            elif allowed and raw not in allowed:
                issue = f"{raw} is not a standard {field} name"
            result[field] = dict(value=raw, raw=raw, source=source, issue=issue)
        result["device"] = self.standardize_device(sdk, row, annotation, sensor_model)
        return result

    def standardize_device(self, sdk, row, annotation, sensor_model):
        """Map the first available device source and flag disagreeing sources."""
        if sdk not in SDKS:
            return dict(value="", raw="", source="", issue="SDK not recognized")
        found = [
            (source, value)
            for source in self.sources["device"][sdk]
            if (value := read_source(source, row, annotation, sensor_model))
        ]
        if not found:
            return dict(value="", raw="", source="", issue="Missing device")
        source, raw = found[0]
        standard = self.device(sdk, raw)
        if standard is None:
            issue = f"{raw} ({source}) is not mapped to a standard device"
            return dict(value=raw, raw=raw, source=source, issue=issue)
        issue = next(
            (
                f"{source} says {standard} but {other} says {other_standard}"
                for other, other_raw in found[1:]
                if (other_standard := self.device(sdk, other_raw))
                and other_standard != standard
            ),
            "",
        )
        return dict(value=standard, raw=raw, source=source, issue=issue)


def first_value(field_sources, row, annotation, sensor_model):
    """Return the first configured source holding a value, else the first source."""
    for source in field_sources:
        value = read_source(source, row, annotation, sensor_model)
        if value:
            return source, value
    return field_sources[0], ""


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
