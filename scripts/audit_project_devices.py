"""Check a project's plan against its captures and the naming file, without writes."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.captures.catalog import records
from app.folder_projects import FolderProjects
from app.captures.naming import load


def planned_fields(project, naming):
    """The naming-file fields this project's matrix plans, in naming-file order."""
    columns = set().union(*(row.keys() for row in project["matrix"]))
    return [field for field in naming.fields if field.key in columns]


def requirement(capture_or_row, fields, values):
    """Build the (batch, SDK, planned field values) key of a capture or matrix row."""
    return (
        capture_or_row["folder"],
        capture_or_row["sdk"],
        *(values(capture_or_row, field.key) for field in fields),
    )


def naming_report(project, captures, naming):
    """Group capture naming issues and list plan values that are not standard names."""
    issues = Counter(
        (field, capture["sdk"], value["raw"], value["issue"])
        for capture in captures
        for field, value in capture["naming"].items()
        if value["issue"]
    )
    plan = sorted(
        {
            (row["folder"], field.key, row[field.key])
            for row in project["matrix"]
            for field in planned_fields(project, naming)
            if field.accepted and row[field.key] not in field.accepted
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


def audit(project, captures, naming):
    """Report batch lists that disagree with the matrix and captures it does not plan.

    Every planned field is checked the same way: a batch's `expected_<field>`
    list must hold exactly the values the matrix plans for that batch, and each
    capture's batch, SDK, and planned field values must match a matrix row.
    """
    fields = planned_fields(project, naming)
    definition_errors = []
    for batch in project["batches"]:
        for field in fields:
            configured = batch.get(f"expected_{field.key}", "")
            if not configured.strip():
                continue
            listed = {v.strip() for v in configured.split(";") if v.strip()}
            planned = {
                row[field.key]
                for row in project["matrix"]
                if row["folder"] == batch["batch_name"]
            }
            if listed != planned:
                definition_errors.append(
                    dict(
                        batch=batch["batch_name"],
                        field=field.key,
                        only_in_batches=sorted(listed - planned),
                        only_in_matrix=sorted(planned - listed),
                    )
                )
    plan = {requirement(r, fields, lambda r, k: r[k]) for r in project["matrix"]}
    unknown = Counter(
        key
        for capture in captures
        for key in [requirement(capture, fields, lambda c, k: c["fields"][k])]
        if key not in plan
    )
    names = ["batch", "sdk", *(field.key for field in fields)]
    return dict(
        definition_errors=definition_errors,
        unplanned_captures=[
            dict(zip(names, key), captures=count)
            for key, count in sorted(unknown.items())
        ],
        **naming_report(project, captures, naming),
    )


def main():
    """Audit one folder project, exiting nonzero when anything does not align."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-root", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--naming", required=True, type=Path, help="Naming file")
    args = parser.parse_args()
    naming = load(args.naming)
    projects = FolderProjects(args.projects_root, args.dataset)
    project = projects.get(args.project)
    captures = projects.filter_records(args.project, records(args.dataset, naming))
    report = audit(project, captures, naming)
    print(json.dumps(report, indent=2))
    return int(any(report.values()))


if __name__ == "__main__":
    raise SystemExit(main())
