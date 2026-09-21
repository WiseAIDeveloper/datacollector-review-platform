"""Copy a CSV pair and review JSON history into a new discoverable project folder."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.folder_projects import FolderProjects
from app.captures.catalog import MATRIX_NAME


def main():
    """Validate inputs, preserve original log snapshots, and publish without overwriting."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    source, destination = args.source.resolve(), args.destination.resolve()
    if destination.exists():
        raise SystemExit("Destination already exists; refusing to overwrite it")
    FolderProjects(source.parent, source).get(source.name)
    paths = [source / f"{MATRIX_NAME}{suffix}.csv" for suffix in ("", "_batches")]
    log_root = source / "capture_viewer/ingestion_logs"
    paths += sorted(log_root.glob("*.json")) + sorted(log_root.glob("*.jsonl"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".import-", dir=destination.parent
    ) as temporary:
        folder = Path(temporary) / destination.name
        folder.mkdir()
        backups = folder / ".imported-history"
        backups.mkdir()
        manifest = {}
        for path in paths:
            if path.is_symlink():
                raise ValueError("Source files must not be symlinks")
            data = path.read_bytes()
            if path.suffix == ".json":
                json.loads(data)
            elif path.suffix == ".jsonl":
                for line in data.splitlines():
                    if line.strip():
                        json.loads(line)
            target = folder / path.name
            target.write_bytes(data)
            target.chmod(0o640)
            if path.parent == log_root:
                shutil.copy2(target, backups / path.name)
            manifest[path.name] = {
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        (folder / "project.json").write_text(
            json.dumps({"name": destination.name}, indent=2) + "\n"
        )
        (backups / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        FolderProjects(folder.parent, source).get(folder.name)
        os.rename(folder, destination)
    print(
        json.dumps(
            {
                "destination": str(destination),
                "copied_files": len(paths),
                "verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
