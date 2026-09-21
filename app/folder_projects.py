"""Discover filesystem projects and isolate their review history."""

import json
import os
import tempfile
import re
import threading
from dataclasses import replace
from pathlib import Path

from .projects import Projects, parse_csv, validate_pair, MATRIX_FIELDS, BATCH_FIELDS
from .captures.catalog import records


class FolderProjects:
    """Discover one CSV pair in each immediate project directory on every request."""

    def __init__(self, directory, root):
        """Retain the project collection and shared capture dataset locations."""
        self.directory, self.root = Path(directory).resolve(), root

    def folder(self, identifier):
        """Confine project identifiers to real immediate child directories."""
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", identifier
        ):
            raise ValueError("Select a valid project")
        folder = self.directory / identifier
        if (
            folder.is_symlink()
            or not folder.is_dir()
            or folder.resolve().parent != self.directory
        ):
            raise ValueError("Unknown project")
        return folder

    def get(self, identifier):
        """Read a project's CSV definitions without a registration database."""
        folder = self.folder(identifier)
        pairs = [
            (path, path.with_name(path.stem + "_batches.csv"))
            for path in folder.glob("*.csv")
            if not path.stem.endswith("_batches")
        ]
        pairs = [(matrix, batches) for matrix, batches in pairs if batches.is_file()]
        if len(pairs) != 1:
            raise ValueError(
                "Project must contain exactly one test-plan CSV and matching _batches.csv"
            )
        matrix_path, batches_path = pairs[0]
        if any(
            path.is_symlink() or path.stat().st_size > 400_000
            for path in (matrix_path, batches_path)
        ):
            raise ValueError("Project CSVs must be regular files up to 400 KB")
        matrix = parse_csv(
            matrix_path.read_text(encoding="utf-8-sig"), MATRIX_FIELDS, "Test plan"
        )
        batches = parse_csv(
            batches_path.read_text(encoding="utf-8-sig"), BATCH_FIELDS, "Batches"
        )
        matrix_name = validate_pair(matrix, batches)
        metadata_path = folder / "project.json"
        metadata = {}
        if metadata_path.exists():
            if metadata_path.is_symlink() or metadata_path.stat().st_size > 10000:
                raise ValueError("Invalid project.json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("Invalid project.json")
        name = metadata.get("name", identifier)
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Invalid project name")
        return dict(
            id=identifier,
            name=name,
            matrix_name=matrix_name,
            matrix=matrix,
            batches=batches,
        )

    def listing(self):
        """List valid projects and display actionable errors for incomplete folders."""
        result = []
        if not self.directory.is_dir():
            return result
        for folder in sorted(self.directory.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            try:
                project = self.get(folder.name)
                result.append(
                    {key: project[key] for key in ("id", "name", "matrix_name")}
                )
            except (ValueError, OSError) as error:
                result.append(dict(id=folder.name, name=folder.name, error=str(error)))
        return result

    def create(self, request):
        """Create a discoverable folder by validating the upload before publishing it."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".upload-", dir=self.directory
        ) as temporary:
            staging = Path(temporary)
            validated = Projects(staging / "validate", self.root).create(request)
            if any(
                p["name"].casefold() == validated["name"].casefold()
                for p in self.listing()
            ):
                raise ValueError("A project with this name already exists")
            slug = (
                re.sub(r"[^A-Za-z0-9_-]+", "_", validated["name"]).strip("_")[:70]
                or "project"
            )
            identifier = slug + "_" + validated["id"][:8]
            folder = staging / identifier
            folder.mkdir()
            (folder / "plan.csv").write_text(request["matrix_csv"], encoding="utf-8")
            (folder / "plan_batches.csv").write_text(
                request["batches_csv"], encoding="utf-8"
            )
            (folder / "project.json").write_text(
                json.dumps({"name": validated["name"]}) + "\n", encoding="utf-8"
            )
            os.rename(folder, self.directory / identifier)
        return dict(validated, id=identifier)

    def filter_records(self, identifier, rows):
        """Scope shared captures to the selected project's batch and test-plan pairs."""
        return Projects.filter_records(self, identifier, rows)


class ProjectApplications:
    """Lazily run a separate review application and history database per project."""

    def __init__(self, settings, application_factory):
        """Avoid starting capture scans until a project is selected."""
        self.settings = settings
        self.projects = FolderProjects(settings.projects_root, settings.root)
        self.factory = application_factory
        self.lock = threading.RLock()
        self.applications = {}
        self.ingestion = self

    def records(self):
        """Resolve globally keyed image links in the shared source capture dataset."""
        return records(self.settings.root)

    def start(self):
        """Project workers start only after a valid selection."""

    def create_project(self, request):
        """Serialize uploads so concurrent project names remain unique."""
        with self.lock:
            return self.projects.create(request)

    def select(self, identifier):
        """Validate the folder and lazily restore its historical logs before scanning."""
        self.projects.get(identifier)
        with self.lock:
            if identifier not in self.applications:
                folder = self.projects.folder(identifier)
                settings = replace(
                    self.settings,
                    database=folder / "ingestion.sqlite",
                    log_path=folder / "ingestion.jsonl",
                    projects_root=None,
                )
                application = self.factory(settings)
                application.lock = self.lock
                application.ingestion.dataset_lock = self.lock
                application.projects = self.projects
                application.project_id = identifier
                try:
                    application.ingestion.restore_logs()
                    application.ingestion.batch_filter = lambda: {
                        (row["batch_name"], row["test_plan_name"])
                        for row in self.projects.get(identifier)["batches"]
                    }
                    application.ingestion.start()
                except Exception:
                    application.ingestion.close()
                    raise
                self.applications[identifier] = application
            return self.applications[identifier]

    def close(self):
        """Stop every project's worker and release its SQLite connection."""
        with self.lock:
            applications = list(self.applications.values())
        for application in applications:
            application.ingestion.close()
