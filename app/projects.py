"""Validate and persist named pairs of collection-plan CSV files."""

import csv
import io
import json
import os
import tempfile
import uuid

from .captures.catalog import MATRIX_NAME, batches, matrix

MATRIX_FIELDS = {
    "matrix_name",
    "folder",
    "lighting",
    "sdk",
    "device",
    "expected_count_per_identity",
}
BATCH_FIELDS = {"batch_name", "test_plan_name", "expected_identities"}


def parse_csv(value, required, label):
    """Reject malformed, empty, oversized, or incomplete plan files."""
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 400_000:
        raise ValueError(f"{label}: select a UTF-8 CSV file up to 400 KB")
    if "\x00" in value:
        raise ValueError(f"{label}: invalid CSV text")
    try:
        reader = csv.DictReader(
            io.StringIO(value.lstrip("\ufeff"), newline=""), strict=True
        )
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not required.issubset(fields):
            raise ValueError(
                f"{label}: required columns: {', '.join(sorted(required))}"
            )
        rows = list(reader)
    except csv.Error as error:
        raise ValueError(f"{label}: malformed CSV") from error
    if not rows or len(rows) > 10000:
        raise ValueError(f"{label}: expected 1–10,000 rows")
    for row in rows:
        if (
            None in row
            or None in row.values()
            or any(not row[key].strip() for key in required)
        ):
            raise ValueError(f"{label}: incomplete or uneven row")
    return rows


class Projects:
    """Keep each validated project in one atomically published state file."""

    def __init__(self, directory, root):
        """Use the existing persistent state volume without moving capture files."""
        self.directory, self.root = directory, root
        directory.mkdir(parents=True, exist_ok=True)

    def listing(self):
        """Return project summaries, including the original dataset when available."""
        result = []
        if all(
            (self.root / f"{MATRIX_NAME}{suffix}.csv").is_file()
            for suffix in ("", "_batches")
        ):
            result.append(
                {
                    "id": "default",
                    "name": "Existing dataset",
                    "matrix_name": MATRIX_NAME,
                }
            )
        for path in sorted(self.directory.glob("*.json")):
            project = json.loads(path.read_text(encoding="utf-8"))
            result.append({key: project[key] for key in ("id", "name", "matrix_name")})
        return result

    def get(self, project_id):
        """Load a project by a confined identifier; never silently fall back."""
        if project_id == "default":
            return {
                "id": "default",
                "name": "Existing dataset",
                "matrix": matrix(self.root),
                "batches": batches(self.root),
            }
        if (
            not isinstance(project_id, str)
            or len(project_id) != 32
            or any(c not in "0123456789abcdef" for c in project_id)
        ):
            raise ValueError("Unknown project")
        try:
            return json.loads(
                (self.directory / f"{project_id}.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise ValueError("Unknown project") from error

    def create(self, request):
        """Validate both files together and publish a project only after all checks pass."""
        if not isinstance(request, dict):
            raise ValueError("Expected a project object")
        name = request.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Project name must be 1–100 characters")
        name = name.strip()
        if any(p["name"].casefold() == name.casefold() for p in self.listing()):
            raise ValueError("A project with this name already exists")
        plan = parse_csv(request.get("matrix_csv"), MATRIX_FIELDS, "Test plan")
        definitions = parse_csv(request.get("batches_csv"), BATCH_FIELDS, "Batches")
        names = {row["matrix_name"] for row in plan}
        if len(names) != 1:
            raise ValueError("Test plan must contain exactly one matrix_name")
        folders = [row["batch_name"] for row in definitions]
        if len(folders) != len(set(folders)):
            raise ValueError("Batches must have unique batch_name values")
        for row in plan:
            if row["folder"] not in folders:
                raise ValueError("Every test-plan folder must match a batch_name")
            if row["sdk"] not in {"web", "app"}:
                raise ValueError("Test-plan sdk must be web or app")
            if (
                not row["expected_count_per_identity"].isascii()
                or not row["expected_count_per_identity"].isdigit()
            ):
                raise ValueError("Expected counts must be non-negative integers")
        keys = [(r["folder"], r["lighting"], r["sdk"], r["device"]) for r in plan]
        if len(keys) != len(set(keys)):
            raise ValueError("Test plan contains duplicate capture requirements")
        project = {
            "id": uuid.uuid4().hex,
            "name": name,
            "matrix_name": next(iter(names)),
            "matrix": plan,
            "batches": definitions,
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = stream.name
                json.dump(project, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / f"{project['id']}.json")
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return {key: project[key] for key in ("id", "name", "matrix_name")}

    def filter_records(self, project_id, rows):
        """Match existing captures by both batch folder and collection test-plan name."""
        project = self.get(project_id)
        pairs = {(b["batch_name"], b["test_plan_name"]) for b in project["batches"]}
        return [
            r
            for r in rows
            if (r["folder"], r["metadata"].get("test_plan_name")) in pairs
        ]
