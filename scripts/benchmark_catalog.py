"""Measure catalog reads and JSON size with a disposable synthetic dataset."""

import argparse
import gzip
import json
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.captures.catalog import CatalogCache, records
from app.captures.naming import Naming
from tests.support import NAMING, dataset


def elapsed(call):
    """Measure one operation without including fixture creation."""
    start = time.perf_counter()
    result = call()
    return time.perf_counter() - start, result


def main():
    """Compare identical uncached and cached workloads, without accessing live data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=int, default=5200)
    args = parser.parse_args()
    if args.captures < 1:
        parser.error("--captures must be positive")
    with tempfile.TemporaryDirectory(prefix="catalog-benchmark-") as directory:
        root = Path(directory)
        dataset(root, count=args.captures)
        naming, cache = Naming(NAMING), CatalogCache(root)
        cold, reference = elapsed(lambda: cache.records(naming))
        original = []
        warmed = []
        for _ in range(3):
            before, baseline = elapsed(lambda: records(root, naming))
            after, current = elapsed(lambda: cache.records(naming))
            assert current == baseline == reference
            original.append(before)
            warmed.append(after)
        body = json.dumps(reference).encode()
        compressed = gzip.compress(body, compresslevel=1, mtime=0)
        assert gzip.decompress(compressed) == body
        with ThreadPoolExecutor(max_workers=4) as pool:
            before, _ = elapsed(
                lambda: list(
                    pool.map(lambda _: json.dumps(records(root, naming)), range(4))
                )
            )
            after, _ = elapsed(
                lambda: list(
                    pool.map(lambda _: json.dumps(cache.records(naming)), range(4))
                )
            )
        print(
            json.dumps(
                {
                    "captures": args.captures,
                    "cold_cache_seconds": round(cold, 4),
                    "uncached_median_seconds": round(statistics.median(original), 4),
                    "cached_median_seconds": round(statistics.median(warmed), 4),
                    "four_concurrent_uncached_seconds": round(before, 4),
                    "four_concurrent_cached_seconds": round(after, 4),
                    "json_bytes": len(body),
                    "gzip_bytes": len(compressed),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
