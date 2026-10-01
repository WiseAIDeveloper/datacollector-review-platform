"""The capture fields shared by every project, defined by the naming file.

Each top-level key of the naming file is one field: its name is the column it is
read from (unless `column` says otherwise), the matrix column that plans it, and
the `expected_<name>` batch column that lists its choices. Key order is display
order. One field has the identity role and one the device role; device spellings
are keyed by the column they are found in, so a label and a detected model code
are never confused.
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


ROLES = ("identity", "device")
COMMON = {"description", "role"}


class Field:
    """One naming-file field: where it is read from and which values it accepts."""

    def __init__(self, key, block):
        """Validate one block; device blocks read a column per SDK."""
        names([key], "field names")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ValueError(f"Naming file: field {key} must be a plain column name")
        if not isinstance(block, dict):
            raise ValueError(f"Naming file: {key} must be an object")
        self.key, self.role = key, block.get("role")
        if self.role is not None and self.role not in ROLES:
            raise ValueError(f"Naming file: {key}.role must be identity or device")
        self.description = description(block, key)
        if self.role == "device":
            self.load_device(block)
        else:
            self.load_value(block)

    def load_value(self, block):
        """Read one column (or its fallback) and accept a list or named spellings."""
        key = self.key
        keys(block, set(), COMMON | {"accepted", "column", "fallback", "required"}, key)
        self.columns = columns(dict(block, column=block.get("column", key)), key)
        self.required = block.get("required", self.role == "identity")
        if not isinstance(self.required, bool):
            raise ValueError(f"Naming file: {key}.required must be true or false")
        accepted = block.get("accepted")
        self.aliases = {}
        if accepted is None:
            # Free text: shown and editable, never flagged except when missing.
            self.accepted = None
            return
        if isinstance(accepted, list):
            empty = self.role == "identity"
            self.accepted = set(names(accepted, f"{key}.accepted", empty))
            return
        if self.role == "identity" or not isinstance(accepted, dict) or not accepted:
            raise ValueError(
                f"Naming file: {key}.accepted must be a list or a nonempty object"
            )
        self.accepted = set(names(list(accepted), f"{key} names"))
        for standard, spellings in accepted.items():
            for raw in names(spellings, f"{key}.accepted.{standard}", True):
                self.add_alias(self.aliases, raw, standard)

    def load_device(self, block):
        """Read a column per SDK; spellings are listed under the column they appear in."""
        key = self.key
        keys(block, {"app", "web", "accepted"}, COMMON, key)
        self.required = True
        self.sdk_columns = {
            sdk: columns(
                keys(block[sdk], {"column"}, {"fallback"}, f"{key}.{sdk}"),
                f"{key}.{sdk}",
            )
            for sdk in SDKS
        }
        self.columns = self.sdk_columns["web"]
        read = {c for order in self.sdk_columns.values() for c in order}
        accepted = block["accepted"]
        if not isinstance(accepted, dict) or not accepted:
            raise ValueError(f"Naming file: {key}.accepted must be a nonempty object")
        self.accepted = set(names(list(accepted), f"{key} names"))
        self.aliases = {column: {} for column in read}
        for device, spellings in accepted.items():
            label = f"{key}.accepted.{device}"
            if not isinstance(spellings, dict) or not set(spellings) <= read:
                raise ValueError(
                    f"Naming file: {label} may only list columns {key}.app/web read: "
                    + ", ".join(sorted(read))
                )
            for column, values in spellings.items():
                for raw in names(values, f"{label}.{column}", allow_empty=True):
                    self.add_alias(self.aliases[column], raw, device)

    def add_alias(self, aliases, raw, standard):
        """Record one spelling, rejecting standard names and ambiguous spellings."""
        if raw in self.accepted:
            raise ValueError(f"Naming file: {raw} is already a standard {self.key}")
        if raw in aliases:
            raise ValueError(
                f"Naming file: {self.key} spelling {raw} maps to two names"
            )
        aliases[raw] = standard

    @property
    def edit_column(self):
        """The index column an edit writes, or None when the field is read elsewhere."""
        column = self.columns[0]
        return None if "." in column else column

    def standard(self, column, raw):
        """Return the standard name of a raw value read from a column, or None."""
        if not self.accepted or raw in self.accepted:
            return raw
        aliases = (
            self.aliases.get(column, {}) if self.role == "device" else self.aliases
        )
        return aliases.get(raw)

    def standardize(self, sdk, row, annotation, sensor_model):
        """Report the standard value, raw value, source column, and any issue."""
        if self.role == "device":
            if sdk not in SDKS:
                return dict(value="", raw="", source="", issue="SDK not recognized")
            order = self.sdk_columns[sdk]
        else:
            order = self.columns
        column, raw = read_first(order, row, annotation, sensor_model)
        # A collector's "na" or older "none" means this optional field is absent.
        # Neither spelling is a standard device name.
        if not raw or (not self.required and raw.casefold() in {"na", "none"}):
            issue = f"Missing {self.key} ({column})" if self.required else ""
            return dict(value="", raw=raw, source=column, issue=issue)
        standard = self.standard(column, raw)
        if standard is None:
            place = f" ({column})" if self.role == "device" else ""
            issue = f"{raw}{place} is not an accepted {self.key}"
            return dict(value=raw, raw=raw, source=column, issue=issue)
        return dict(value=standard, raw=raw, source=column, issue="")

    def describe(self):
        """Describe the field for pages: name, role, edit column, choices."""
        return dict(
            key=self.key,
            description=self.description,
            role=self.role,
            column=self.edit_column,
            required=self.required,
            accepted=None if self.accepted is None else sorted(self.accepted),
        )


class Naming:
    """A validated naming document: its fields in display order."""

    def __init__(self, document):
        """Require exactly one identity and one device field."""
        if not isinstance(document, dict) or not document:
            raise ValueError("Naming file must be an object with at least one field")
        self.fields = [Field(key, block) for key, block in document.items()]
        for role in ROLES:
            matches = [field for field in self.fields if field.role == role]
            if len(matches) != 1:
                raise ValueError(
                    f"Naming file needs exactly one field with role {role}"
                )
            setattr(self, role, matches[0])
        self.dimensions = [field for field in self.fields if field.role is None]
        columns = [f.edit_column for f in self.fields if f.edit_column]
        if len(columns) != len(set(columns)):
            raise ValueError("Naming file: two fields read the same column")

    def field(self, key):
        """Return the field with this name, or None."""
        return next((field for field in self.fields if field.key == key), None)

    def editable(self):
        """Map each index column an edit may write to its field."""
        return {f.edit_column: f for f in self.fields if f.edit_column}

    def standardize(self, sdk, row, annotation, sensor_model):
        """Standardize every field of one capture, keyed by field name."""
        return {
            field.key: field.standardize(sdk, row, annotation, sensor_model)
            for field in self.fields
        }

    def describe(self):
        """Describe every field in display order for the pages."""
        return [field.describe() for field in self.fields]


def required_naming(settings):
    """The naming file defines the fields every page shows, so it is required."""
    if not settings.naming_file:
        raise ValueError("Set NAMING_FILE to the naming file that defines the fields")
    return settings.naming_file


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
