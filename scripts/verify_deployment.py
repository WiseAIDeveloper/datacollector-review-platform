"""Record and compare deployment behavior without printing dataset records or secrets."""

import argparse
import hashlib
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def digest(value):
    """Hash canonical JSON so reports contain no capture metadata."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fetch(base, path):
    """Read a public API or image directly, retaining error responses for comparison."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(base + path, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        kind = response.headers.get_content_type()
        value = json.loads(body) if kind == "application/json" else body
        return response.status, kind, value


def response_summary(base, path):
    """Summarize status, media type, and content without storing raw response data."""
    status, kind, value = fetch(base, path)
    if isinstance(value, dict) and "last_scan" in value:
        value = {
            key: item
            for key, item in value.items()
            if key not in {"last_scan", "scanning", "new_entries"}
        }
    content_hash = (
        hashlib.sha256(value).hexdigest() if isinstance(value, bytes) else digest(value)
    )
    return {"status": status, "content_type": kind, "sha256": content_hash}


def snapshot(container, base):
    """Capture service restrictions, public API results, and persistent-history hashes."""
    inspection = json.loads(subprocess.check_output(["docker", "inspect", container]))[
        0
    ]
    host = inspection["HostConfig"]
    report = {
        "image": inspection["Image"],
        "running": inspection["State"]["Running"],
        "health": inspection["State"].get("Health", {}).get("Status"),
        "configuration": {
            "ports": host["PortBindings"],
            "read_only": host["ReadonlyRootfs"],
            "cap_drop": host["CapDrop"],
            "security_opt": host["SecurityOpt"],
            "restart_policy": host["RestartPolicy"],
            "mounts": [
                {
                    key: mount.get(key)
                    for key in ("Type", "Source", "Destination", "RW", "Name")
                }
                for mount in inspection["Mounts"]
                if mount["Destination"] in {"/data", "/state", "/logs"}
            ],
        },
        "api": {},
    }
    for path in (
        "/health",
        "/api/captures",
        "/api/matrix",
        "/api/batches",
        "/api/quality",
        "/api/ingestion?limit=500",
    ):
        report["api"][path] = response_summary(base, path)
    status, _, captures = fetch(base, "/api/captures")
    if status != 200:
        raise RuntimeError("Capture API is unavailable")
    report["capture_count"] = len(captures)
    for index, row in enumerate(captures[:5]):
        key = urllib.parse.quote(row["key"])
        for route in ("capture", "image", "annotation"):
            report["api"][f"/api/{route}[sample-{index}]"] = response_summary(
                base, f"/api/{route}?key={key}"
            )
        report["api"][f"/api/search[sample-{index}]"] = response_summary(
            base, "/api/search?q=" + urllib.parse.quote(row["metadata"]["uuid"])
        )
    code = """
import hashlib, json, sqlite3
from pathlib import Path
db = sqlite3.connect('file:/state/ingestion.sqlite?mode=ro', uri=True)
db.execute('BEGIN')
report = {}
for table in ('events', 'actions', 'meta'):
    rows = db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
    report[table] = {'count': len(rows), 'sha256': hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
db.close()
report['logs'] = {name: hashlib.sha256((Path('/logs') / name).read_bytes()).hexdigest()
                  for name in ('ingestion.jsonl', 'actions.jsonl', 'quality_reviews.json')
                  if (Path('/logs') / name).is_file()}
report['source'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in Path('/app').iterdir() if path.suffix in ('.py', '.html', '.css', '.js')}
print(json.dumps(report))
"""
    state = json.loads(
        subprocess.check_output(["docker", "exec", container, "python", "-c", code])
    )
    report["source"] = state.pop("source")
    report["persistent_state"] = state
    return report


def compare(before, after):
    """Require identical service restrictions, data responses, and persisted review history."""
    # Docker does not guarantee mount listing order; destinations define their meaning.
    before = dict(
        before, configuration=canonical_configuration(before["configuration"])
    )
    after = dict(after, configuration=canonical_configuration(after["configuration"]))
    differences = [
        key
        for key in ("configuration", "api", "capture_count", "persistent_state")
        if before[key] != after[key]
    ]
    if differences:
        raise SystemExit("Deployment differs in: " + ", ".join(differences))
    if not after["running"] or after["health"] != "healthy":
        raise SystemExit("New deployment is not running and healthy")
    print(
        f"PASS deployment parity: {after['capture_count']} captures, {len(after['api'])} API comparisons, unchanged persistent history and container restrictions."
    )


def canonical_configuration(configuration):
    """Compare mounts by destination while retaining their sources and access modes."""
    return dict(
        configuration,
        mounts=sorted(configuration["mounts"], key=lambda mount: mount["Destination"]),
    )


def main():
    """Save a private snapshot or compare two previously captured deployment reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("snapshot")
    capture.add_argument("--container", required=True)
    capture.add_argument("--url", required=True)
    capture.add_argument("--output", type=Path, required=True)
    comparison = subparsers.add_parser("compare")
    comparison.add_argument("before", type=Path)
    comparison.add_argument("after", type=Path)
    args = parser.parse_args()
    if args.command == "snapshot":
        report = snapshot(args.container, args.url)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        args.output.chmod(0o600)
        print(
            f"Recorded {report['capture_count']} captures and {len(report['api'])} API summaries; data and credential values withheld."
        )
    else:
        compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))


if __name__ == "__main__":
    main()
