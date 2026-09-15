"""Characterize dataset-reading functions from both the original and current app."""

import ast
import csv
import json
import tempfile
import types
import unittest
from pathlib import Path

from tests.support import INDEXES, MATRIX_NAME, SOURCE, dataset, write_csv


def catalog_for(root):
    """Load original reader functions without running the old server's startup code."""
    if (SOURCE / "capture_data.py").exists():
        import capture_data

        return types.SimpleNamespace(
            records=lambda: capture_data.records(root),
            matrix=lambda: capture_data.matrix(root),
            batches=lambda: capture_data.batches(root),
            collection_annotation=capture_data.collection_annotation,
        )
    tree = ast.parse((SOURCE / "server.py").read_text())
    tree.body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"records", "matrix", "batches", "collection_annotation"}
    ]
    module = types.ModuleType("original_catalog")
    module.__dict__.update(
        ast=ast,
        csv=csv,
        json=json,
        Path=Path,
        ROOT=root,
        MATRIX_NAME=MATRIX_NAME,
        MATRIX_PATH=root / f"{MATRIX_NAME}.csv",
        BATCHES_PATH=root / f"{MATRIX_NAME}_batches.csv",
    )
    exec(compile(tree, str(SOURCE / "server.py"), "exec"), module.__dict__)
    return module


class CatalogTests(unittest.TestCase):
    """Preserve annotation fallback, ordering, matrix selection, and legacy devices."""

    def setUp(self):
        """Create a catalog backed by synthetic rows and definitions."""
        temporary = tempfile.TemporaryDirectory(prefix="catalog-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rows = dataset(self.root, count=5)
        self.catalog = catalog_for(self.root)

    def test_annotation_missing_and_malformed_fallbacks(self):
        """Missing or malformed collection JSON produces an empty annotation."""
        folder = self.root / "genuine"
        self.assertEqual(self.catalog.collection_annotation(folder, "missing"), {})
        path = folder / "mykadfront/datacollector_annotation/capture-0.json"
        path.write_text("{")
        self.assertEqual(self.catalog.collection_annotation(folder, "capture-0"), {})
        self.assertEqual(self.catalog.records()[0]["annotation_lighting"], "")

    def test_records_keep_legacy_device_values_and_order(self):
        """Catalog parsing preserves raw non-dict sensors and the original empty fallback."""
        sensors = [
            "{'model': 'phone'}",
            "{'model': 123}",
            "['raw', 'sensor']",
            "model:phone,os:value",
            "",
        ]
        for row, sensor in zip(self.rows, sensors):
            row.update(capture_device="", input_sensor=sensor)
        write_csv(self.root / "genuine" / INDEXES[0], self.rows)
        records = self.catalog.records()
        self.assertEqual(
            [row["device"] for row in records],
            ["phone", 123, "['raw', 'sensor']", "phone", ""],
        )
        self.assertEqual([row["sdk"] for row in records], ["app"] * 5)
        self.assertEqual([row["line"] for row in records], [2, 3, 4, 5, 6])
        self.assertEqual([row["metadata"] for row in records], self.rows)

    def test_excluded_folders_are_not_catalogued(self):
        """Ignore administrative and excluded batches even when they contain valid indexes."""
        for name in ("test", "webcam_genuine", "webcam_replay", "capture_viewer"):
            folder = self.root / name
            folder.mkdir()
            write_csv(folder / INDEXES[0], self.rows)
        self.assertEqual(len(self.catalog.records()), 5)

    def test_matrix_filters_other_plans_and_batches_preserve_rows(self):
        """Only the configured matrix is selected while all batch definitions are retained."""
        path = self.root / f"{MATRIX_NAME}.csv"
        with path.open() as stream:
            rows = list(csv.DictReader(stream))
        write_csv(path, [rows[0], {**rows[0], "matrix_name": "other"}])
        self.assertEqual(self.catalog.matrix(), rows)
        self.assertEqual(
            self.catalog.batches()[0]["expected_identities"], "fixture;another"
        )


if __name__ == "__main__":
    unittest.main()
