"""Characterize dataset-reading functions from both the original and current app."""

import csv
import tempfile
import types
import unittest
from pathlib import Path

from tests.support import (
    INDEXES,
    MATRIX_NAME,
    NAMING,
    dataset,
    load_application,
    write_csv,
)


def catalog_for(root):
    """Bind the catalog readers to one fixture dataset and the fixture fields."""
    capture_data = load_application("capture_data")
    naming = load_application("naming").Naming(NAMING)
    return types.SimpleNamespace(
        records=lambda: capture_data.records(root, naming),
        matrix=lambda: capture_data.matrix(root),
        batches=lambda: capture_data.batches(root),
        collection_annotation=capture_data.collection_annotation,
    )


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
        record = self.catalog.records()[0]
        self.assertEqual(record["annotation"]["capture_env_lighting"], "")
        self.assertEqual(self.catalog.records()[1]["annotation"]["subject"], "")

    def test_records_classify_known_sensors_and_keep_order(self):
        """Known app sensors are recognized; unsupported values remain explicitly unknown."""
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
            ["phone", "unknown", "unknown", "phone", "unknown"],
        )
        self.assertEqual(
            [row["sdk"] for row in records],
            ["app", "unknown", "unknown", "app", "unknown"],
        )
        self.assertEqual([row["line"] for row in records], [2, 3, 4, 5, 6])
        self.assertEqual([row["metadata"] for row in records], self.rows)

    def test_sdk_detection_uses_sensor_before_device_label(self):
        """Catalog and ingestion agree on web, native, legacy iOS, and unknown sensors.

        The SDK comes from the sensor; the device is the label when there is one,
        else the App SDK's detected model, as the naming file's device field says.
        """
        catalog = load_application("capture_data")
        ingestion = load_application("ingestion")
        naming = load_application("naming").Naming(NAMING)
        cases = [
            ("websdk;chromemobile;android;mobile", "web", "JNY-LX2"),
            (" WEBSdk;browser ", "web", "unknown"),
            ("{'manufacturer': 'HUAWEI', 'model': 'JNY-LX2'}", "app", "JNY-LX2"),
            (
                '{"manufacturer":"Apple","model":"iPhone14","flag":true}',
                "app",
                "iPhone14",
            ),
            ("model:iPhone14,ios:26.2", "app", "iPhone14"),
            ("model:Unknown,ios:26.5", "app", "unknown"),
            ("model: UNKNOWN ,ios:26.5", "app", "unknown"),
            ('{"model":"Unknown"}', "app", "unknown"),
            ("", "unknown", "unknown"),
            ("unrecognized", "unknown", "unknown"),
            ("{broken", "unknown", "unknown"),
            ("{}", "unknown", "unknown"),
            ("{'model': 123}", "unknown", "unknown"),
            ("model:,ios:26.2", "unknown", "unknown"),
        ]
        for sensor, sdk, device in cases:
            with self.subTest(sensor=sensor):
                row = {"input_sensor": sensor}
                if sdk == "web" and device != "unknown":
                    row["capture_device"] = device
                found, fields = catalog.capture_fields(naming, row, {})
                self.assertEqual(
                    (found, fields["capture_device"]["value"]), (sdk, device)
                )
                self.assertEqual(ingestion.logged_fields(naming, row)[0], sdk)
        labelled = {"input_sensor": "model:iPhone14", "capture_device": "iphone-13"}
        self.assertEqual(
            catalog.capture_fields(naming, labelled, {})[1]["capture_device"]["value"],
            "iphone-13",
        )

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
            self.catalog.batches()[0]["expected_subject"], "fixture;another"
        )


if __name__ == "__main__":
    unittest.main()
