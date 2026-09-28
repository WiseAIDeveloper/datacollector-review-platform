"""Check project device definitions against current collector metadata without writes."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.captures.catalog import records
from app.folder_projects import FolderProjects
from app.captures.naming import load


def naming_report(project, captures, naming):
    """Group capture naming issues and list plan values that are not standard names."""
    issues = Counter(
        (field, capture["sdk"], value["raw"], value["issue"])
        for capture in captures
        for field, value in capture.get("naming", {}).items()
        if value["issue"]
    )
    plan = sorted(
        {
            (row["folder"], field, row[field])
            for row in project["matrix"]
            for field, allowed in (
                ("lighting", naming.lighting),
                ("device", naming.devices),
            )
            if row[field] not in allowed
        }
    )
    return dict(
        naming_issues=[
            dict(field=field, sdk=sdk, raw=raw, issue=issue, captures=count)
            for (field, sdk, raw, issue), count in sorted(issues.items())
        ],
        nonstandard_plan_values=[
            dict(batch=folder, field=field, value=value)
            for folder, field, value in plan
        ],
    )


def audit(project, captures, naming=None):
    """Report inconsistent planning lists and observed SDK/device pairs absent from the matrix.

    With a naming document, also report capture naming issues and plan values
    that are not standard names.
    """
    matrix_pairs = {(r["folder"], r["sdk"], r["device"]) for r in project["matrix"]}
    definition_errors = []
    for batch in project["batches"]:
        for sdk in ("app", "web"):
            configured = batch.get(f"expected_{sdk}_devices", "")
            if not configured.strip():
                continue
            devices = {v.strip() for v in configured.split(";") if v.strip()}
            planned = {
                device
                for folder, platform, device in matrix_pairs
                if folder == batch["batch_name"] and platform == sdk
            }
            if devices != planned:
                definition_errors.append(
                    dict(
                        batch=batch["batch_name"],
                        sdk=sdk,
                        only_in_batches=sorted(devices - planned),
                        only_in_matrix=sorted(planned - devices),
                    )
                )
    unknown = Counter(
        (r["folder"], r["sdk"], r["device"])
        for r in captures
        if (r["folder"], r["sdk"], r["device"]) not in matrix_pairs
    )
    report = dict(
        definition_errors=definition_errors,
        unmatched_devices=[
            dict(batch=folder, sdk=sdk, device=device, captures=count)
            for (folder, sdk, device), count in sorted(unknown.items())
        ],
    )
    if naming is not None:
        report.update(naming_report(project, captures, naming))
    return report


def main():
    """Audit one folder project, exiting nonzero when device definitions do not align."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-root", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--naming", type=Path, help="Shared naming JSON file")
    args = parser.parse_args()
    naming = load(args.naming) if args.naming else None
    projects = FolderProjects(args.projects_root, args.dataset)
    project = projects.get(args.project)
    captures = projects.filter_records(args.project, records(args.dataset, naming))
    report = audit(project, captures, naming)
    print(json.dumps(report, indent=2))
    return int(any(report.values()))


if __name__ == "__main__":
    raise SystemExit(main())
