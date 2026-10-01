"""Measure dashboard API latency on a disposable server, never the live service."""

import argparse
import json
import math
import statistics
import shutil
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.server import create_server
from app.settings import Settings
from tests.support import NAMING, MATRIX_NAME, dataset


def main():
    """Time cold and concurrent HTTP reads with generated captures and no live data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=int, default=5200)
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument(
        "--folder-project",
        action="store_true",
        help="Include project selection and its live ingestion worker",
    )
    args = parser.parse_args()
    if args.captures < 1 or not 1 <= args.users <= 128:
        parser.error("captures must be positive; users must be between 1 and 128")
    with tempfile.TemporaryDirectory(prefix="dashboard-http-benchmark-") as directory:
        root = Path(directory)
        dataset(root, count=args.captures)
        naming = root / "naming.json"
        naming.write_text(json.dumps(NAMING))
        projects_root = None
        if args.folder_project:
            projects_root = root / "project-folders"
            folder = projects_root / "fixture"
            folder.mkdir(parents=True)
            for suffix in (".csv", "_batches.csv"):
                shutil.copy2(root / (MATRIX_NAME + suffix), folder / ("plan" + suffix))
        settings = Settings(
            root=root,
            database=root / "history.sqlite",
            log_path=root / "ingestion.jsonl",
            delete_token="",
            write_pin_required=False,
            naming_file=naming,
            host="127.0.0.1",
            port=0,
            projects_root=projects_root,
        )
        server = create_server(settings)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/api/captures"
        if args.folder_project:
            url += "?project=fixture"

        def request(_=None):
            """Measure response delivery and retain only timing and byte counts."""
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            start = time.perf_counter()
            with opener.open(
                urllib.request.Request(url, headers={"Accept-Encoding": "gzip"}),
                timeout=120,
            ) as response:
                body = response.read()
                assert response.status == 200
                encoding = response.headers.get("Content-Encoding")
            return time.perf_counter() - start, len(body), encoding

        try:
            cold = request()
            # Check one response's contents outside the timed concurrent workload.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            assert len(json.load(opener.open(url))) == args.captures
            barrier = threading.Barrier(args.users)

            def concurrent_request(index):
                """Begin each simulated browser's request at the same time."""
                barrier.wait(timeout=10)
                return request(index)

            with ThreadPoolExecutor(max_workers=args.users) as pool:
                start = time.perf_counter()
                samples = list(pool.map(concurrent_request, range(args.users)))
                duration = time.perf_counter() - start
            latencies = sorted(item[0] for item in samples)
            print(
                json.dumps(
                    dict(
                        captures=args.captures,
                        concurrent_users=args.users,
                        cold_seconds=round(cold[0], 4),
                        p50_seconds=round(statistics.median(latencies), 4),
                        p95_seconds=round(
                            latencies[math.ceil(len(latencies) * 0.95) - 1], 4
                        ),
                        burst_seconds=round(duration, 4),
                        response_bytes=samples[0][1],
                        content_encoding=samples[0][2],
                        ingestion_worker=(
                            "enabled (folder project)"
                            if args.folder_project
                            else "disabled to isolate HTTP/catalog cost"
                        ),
                    ),
                    indent=2,
                )
            )
        finally:
            server.shutdown()
            worker.join()
            server.server_close()
            server.application.ingestion.close()


if __name__ == "__main__":
    main()
