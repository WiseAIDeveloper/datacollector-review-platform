"""Validate the shared naming file and its effect on capture records and edits."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.support import INDEXES, SOURCE, dataset, running_server, write_csv

if not (SOURCE / "app/captures/naming.py").is_file():
    raise unittest.SkipTest("Naming files are not part of this source revision")

from app.captures import catalog, naming
from app.captures.editing import Conflict, edit_capture

FIELDS = {
    "lighting": "lighting",
    "identity": "subject",
    "app_device": "input_sensor.model",
    "web_device": "capture_device",
}
SOURCES = {key: {"field": field} for key, field in FIELDS.items()}
SOURCES["app_device"]["description"] = "Native model reported by the App SDK"
DOCUMENT = {
    "sources": SOURCES,
    "lighting": ["office_white", "office_yellow", "office_dark", "random_bg"],
    "devices": {
        "galaxy_z_fold_5": {"model": ["SM-F946U1"]},
        "iphone_13": {"label": ["iphone-13"]},
    },
    "identities": ["fixture", "another"],
}
SENSOR = "input_sensor.model"
FOLD_SENSOR = "{'manufacturer': 'samsung', 'model': 'SM-F946U1'}"


def document(**changes):
    """Return a copy of the sample naming document with top-level overrides."""
    return {**json.loads(json.dumps(DOCUMENT)), **changes}


class NamingDocumentTests(unittest.TestCase):
    """Reject naming files that would be ambiguous or silently misread."""

    def test_valid_document_builds_aliases(self):
        """Aliases resolve per SDK and a standard name always matches itself."""
        names = naming.Naming(document())
        self.assertEqual(names.device(SENSOR, "SM-F946U1"), "galaxy_z_fold_5")
        self.assertEqual(
            names.device("capture_device", "galaxy_z_fold_5"), "galaxy_z_fold_5"
        )
        self.assertEqual(names.device("capture_device", "iphone-13"), "iphone_13")
        self.assertIsNone(names.device("capture_device", "SM-F946U1"))
        self.assertIsNone(names.device(SENSOR, "iphone-13"))
        self.assertEqual(names.sources, FIELDS)
        self.assertEqual(
            names.source_descriptions["app_device"],
            "Native model reported by the App SDK",
        )
        self.assertEqual(names.source_descriptions["lighting"], "")

    def test_invalid_documents(self):
        """Unknown keys, duplicates, conflicting aliases, and bad sources fail."""
        cases = {
            "unknown key": document(colour=[]),
            "empty lighting": document(lighting=[]),
            "duplicate lighting": document(lighting=["office_white"] * 2),
            "untrimmed identity": document(identities=[" fixture"]),
            "sdk alias keys": document(devices={"phone": {"app": ["x"]}}),
            "alias twice": document(
                devices={"a": {"model": ["X1"]}, "b": {"model": ["X1"]}}
            ),
            "alias is a name": document(devices={"a": {"label": ["b"]}, "b": {}}),
            "sources missing": {k: v for k, v in DOCUMENT.items() if k != "sources"},
            "source incomplete": document(
                sources={k: v for k, v in SOURCES.items() if k != "web_device"}
            ),
            "source is text": document(sources=dict(SOURCES, lighting="lighting")),
            "bad source": document(
                sources=dict(SOURCES, lighting={"field": "../lighting"})
            ),
            "extra source key": document(
                sources=dict(SOURCES, lighting={"field": "lighting", "x": 1})
            ),
            "bad source description": document(
                sources=dict(SOURCES, lighting={"field": "lighting", "description": 5})
            ),
            "device description": document(devices={"a": {"description": "Phone"}}),
            "file description": document(description="x"),
            "fallback repeats field": document(
                sources=dict(
                    SOURCES, lighting={"field": "lighting", "fallback": "lighting"}
                )
            ),
            "bad fallback": document(
                sources=dict(SOURCES, lighting={"field": "lighting", "fallback": 3})
            ),
        }
        for label, value in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                naming.Naming(value)

    def test_models_and_labels_are_separate_namespaces(self):
        """A sensor model code and a device label may share text but differ."""
        names = naming.Naming(
            document(devices={"a": {"model": ["X1"]}, "b": {"label": ["X1"]}})
        )
        self.assertEqual(
            (names.device(SENSOR, "X1"), names.device("capture_device", "X1")),
            ("a", "b"),
        )


class StandardizeTests(unittest.TestCase):
    """Report standard values, raw values, sources, and issues per field."""

    def setUp(self):
        """Use the sample naming document."""
        self.names = naming.Naming(document())

    def standardize(self, sdk, row, annotation=None, model=""):
        """Standardize one synthetic CSV row."""
        return self.names.standardize(sdk, row, annotation or {}, model)

    def test_standard_values_have_no_issues(self):
        """Allowed lighting and identity pass; an app model maps to its device."""
        result = self.standardize(
            "app",
            {"lighting": "office_dark", "subject": "fixture"},
            model="SM-F946U1",
        )
        self.assertEqual(
            result["device"],
            dict(
                value="galaxy_z_fold_5",
                raw="SM-F946U1",
                source="input_sensor.model",
                issue="",
            ),
        )
        self.assertEqual(result["lighting"]["issue"], "")
        self.assertEqual(result["identity"]["issue"], "")

    def test_nonstandard_values_are_flagged_not_changed(self):
        """Lighting is never translated; unknown names keep their raw value."""
        result = self.standardize(
            "app", {"lighting": "white", "subject": "stranger"}, model="SM-A556E"
        )
        self.assertEqual(result["lighting"]["value"], "white")
        self.assertIn("not a standard lighting", result["lighting"]["issue"])
        self.assertIn("not a standard identity", result["identity"]["issue"])
        self.assertEqual(result["device"]["value"], "SM-A556E")
        self.assertIn("not mapped", result["device"]["issue"])

    def test_missing_values(self):
        """Empty sources are reported as missing."""
        result = self.standardize("web", {})
        self.assertEqual(result["lighting"]["issue"], "Missing lighting (lighting)")
        self.assertEqual(result["device"]["issue"], "Missing device (capture_device)")
        self.assertEqual(
            self.standardize("unknown", {})["device"]["issue"], "SDK not recognized"
        )

    def test_app_device_reads_label_then_detected_model(self):
        """The App label has priority; an empty label falls back to the sensor model."""
        names = naming.Naming(
            document(
                sources=dict(
                    SOURCES,
                    app_device={
                        "field": "capture_device",
                        "fallback": "input_sensor.model",
                    },
                )
            )
        )
        cases = [
            (
                {"capture_device": "iphone_13"},
                "SM-F946U1",
                "iphone_13",
                "capture_device",
            ),
            (
                {"capture_device": "iphone-13"},
                "SM-F946U1",
                "iphone_13",
                "capture_device",
            ),
            ({"capture_device": ""}, "SM-F946U1", "galaxy_z_fold_5", SENSOR),
            ({"capture_device": " "}, "Unknown", "", "capture_device"),
        ]
        for row, model, value, column in cases:
            with self.subTest(row=row, model=model):
                device = names.standardize("app", row, {}, model)["device"]
                self.assertEqual((device["value"], device["source"]), (value, column))
        self.assertEqual(
            names.standardize("app", {}, {}, "")["device"]["issue"],
            "Missing device (capture_device)",
        )

    def test_without_fallback_only_the_field_is_read(self):
        """No fallback means an empty field is missing, even with a sensor model."""
        device = self.standardize(
            "app", {"capture_device": "galaxy_z_fold_5"}, model="Unknown"
        )["device"]
        self.assertEqual(device["issue"], "Missing device (input_sensor.model)")

    def test_configured_sources(self):
        """Fields can be read from another column or the collection annotation."""
        names = naming.Naming(
            document(
                sources=dict(
                    SOURCES,
                    lighting={"field": "annotation.lighting"},
                    identity={"field": "person"},
                )
            )
        )
        result = names.standardize(
            "web",
            {"lighting": "white", "person": "another", "capture_device": "iphone-13"},
            {"lighting": "office_white"},
            "",
        )
        self.assertEqual(result["lighting"]["value"], "office_white")
        self.assertEqual(result["lighting"]["source"], "annotation.lighting")
        self.assertEqual(result["identity"]["value"], "another")
        self.assertEqual(result["device"]["value"], "iphone_13")


class NamingFileTests(unittest.TestCase):
    """Reload changes, but never replace a valid document with a broken one."""

    def setUp(self):
        """Write the sample document to a disposable file."""
        temporary = tempfile.TemporaryDirectory(prefix="naming-test-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "naming.json"
        self.write(document())

    def write(self, value, stamp=None):
        """Write a document and give it a distinct modification time."""
        self.path.write_text(json.dumps(value) if not isinstance(value, str) else value)
        if stamp is not None:
            os.utime(self.path, ns=(stamp, stamp))

    def test_startup_requires_valid_file(self):
        """A broken file stops startup instead of disabling checks."""
        self.write("{")
        with self.assertRaises(ValueError):
            naming.NamingFile(self.path)

    def test_reload_keeps_last_valid_version(self):
        """Edits apply without restart; a broken edit reports an error."""
        names = naming.NamingFile(self.path)
        self.write(document(identities=["new-person"]), stamp=10**18)
        self.assertEqual(names.current().identities, {"new-person"})
        self.write("{", stamp=2 * 10**18)
        self.assertEqual(names.current().identities, {"new-person"})
        self.assertIn("not reloaded", names.error)
        self.write(document(), stamp=3 * 10**18)
        self.assertEqual(names.current().identities, {"fixture", "another"})
        self.assertEqual(names.error, "")


class DatasetTests(unittest.TestCase):
    """Apply the naming file to catalog records and metadata edits."""

    def setUp(self):
        """Create a disposable dataset with one app capture."""
        temporary = tempfile.TemporaryDirectory(prefix="naming-data-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rows = dataset(self.root, count=2)
        self.rows[1].update(capture_device="", input_sensor=FOLD_SENSOR)
        self.rows[1]["lighting"] = "office_white"
        write_csv(self.root / "genuine" / INDEXES[0], self.rows)
        self.names = naming.Naming(document())

    def test_records_without_naming_are_unchanged(self):
        """No naming file keeps raw devices and adds CSV lighting and identity."""
        record = catalog.records(self.root)[1]
        self.assertEqual(record["device"], "SM-F946U1")
        self.assertEqual(
            (record["lighting"], record["identity"]), ("office_white", "fixture")
        )
        self.assertNotIn("naming", record)

    def test_records_with_naming(self):
        """Devices are standardized and nonstandard values carry issues."""
        web, app = catalog.records(self.root, self.names)
        self.assertEqual(
            (web["device"], app["device"]), ("iphone_13", "galaxy_z_fold_5")
        )
        self.assertIn("not a standard lighting", web["naming"]["lighting"]["issue"])
        self.assertEqual(app["naming"]["lighting"]["issue"], "")
        self.assertEqual(app["metadata"], self.rows[1])

    def test_edits_require_standard_names(self):
        """Edits reject lighting, identity, and devices outside the naming file."""
        row = self.rows[0]
        for changes in (
            {"lighting": "dark"},
            {"subject": "stranger"},
            {"capture_device": "iphone-13"},
        ):
            with self.subTest(changes), self.assertRaises(ValueError) as caught:
                edit_capture(
                    self.root,
                    "genuine",
                    row["uuid"],
                    row["filename"],
                    changes,
                    row,
                    naming=self.names,
                )
            self.assertNotIsInstance(caught.exception, Conflict)
        result = edit_capture(
            self.root,
            "genuine",
            row["uuid"],
            row["filename"],
            {"lighting": "office_dark", "capture_device": "iphone_13"},
            row,
            naming=self.names,
        )
        self.assertTrue(result["updated"])


class ServerTests(unittest.TestCase):
    """Serve naming reports through the capture and ingestion APIs."""

    def test_ingestion_reports_naming_issues(self):
        """Ingestion events carry per-field issues from the current naming file."""
        with running_server(naming=document()) as client:
            events = client.request("/api/ingestion")[1]["events"]
            self.assertEqual(len(events), 5)
            event = events[0]
            self.assertEqual(event["device"], "iphone_13")
            self.assertEqual(event["lighting"], "dark")
            self.assertIn(
                "not a standard lighting", event["naming"]["lighting"]["issue"]
            )
            self.assertEqual(event["naming"]["identity"]["issue"], "")
            record = client.request("/api/captures")[1][0]
            self.assertEqual(record["naming"], event["naming"])


if __name__ == "__main__":
    unittest.main()
