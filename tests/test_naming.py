"""Validate the shared naming file and its effect on capture records and edits."""

import copy
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

SENSOR = "input_sensor.model"
DOCUMENT = {
    "lighting": {
        "description": "Lighting chosen in the collector",
        "column": "lighting",
        "accepted": ["office_white", "office_yellow", "office_dark", "random_bg"],
    },
    "identity": {"column": "subject", "accepted": ["fixture", "another"]},
    "device": {
        "description": "Phone used for the capture",
        "app": {"column": "capture_device", "fallback": SENSOR},
        "web": {"column": "capture_device"},
        "accepted": {
            "galaxy_z_fold_5": {SENSOR: ["SM-F946U1"]},
            "iphone_13": {"capture_device": ["iphone-13"]},
        },
    },
}
FOLD_SENSOR = "{'manufacturer': 'samsung', 'model': 'SM-F946U1'}"


def document(**blocks):
    """Return a copy of the sample document with blocks updated key by key."""
    result = copy.deepcopy(DOCUMENT)
    for field, changes in blocks.items():
        if changes is None:
            del result[field]
        elif field in result:
            result[field].update(changes)
        else:
            result[field] = changes
    return result


def with_identities(accepted):
    """Return the sample document with another accepted identity list."""
    return document(identity={"accepted": accepted})


class NamingDocumentTests(unittest.TestCase):
    """Reject naming files that would be ambiguous or silently misread."""

    def test_valid_document(self):
        """Columns, descriptions, and column-keyed device spellings are loaded."""
        names = naming.Naming(document())
        self.assertEqual(
            names.columns,
            {
                "lighting": ("lighting",),
                "identity": ("subject",),
                "app_device": ("capture_device", SENSOR),
                "web_device": ("capture_device",),
            },
        )
        self.assertEqual(names.lighting, set(DOCUMENT["lighting"]["accepted"]))
        self.assertEqual(names.descriptions["identity"], "")
        self.assertEqual(names.device(SENSOR, "SM-F946U1"), "galaxy_z_fold_5")
        self.assertEqual(names.device("capture_device", "iphone-13"), "iphone_13")
        self.assertEqual(names.device(SENSOR, "iphone_13"), "iphone_13")
        self.assertIsNone(names.device("capture_device", "SM-F946U1"))
        self.assertIsNone(names.device(SENSOR, "iphone-13"))

    def test_invalid_documents(self):
        """Unknown keys, duplicates, conflicting spellings, and bad columns fail."""
        accepted = DOCUMENT["device"]["accepted"]
        cases = {
            "unknown top key": document(colour={}),
            "missing block": document(identity=None),
            "unknown block key": document(lighting={"values": []}),
            "no lighting": document(lighting={"accepted": []}),
            "duplicate lighting": document(lighting={"accepted": ["office_dark"] * 2}),
            "untrimmed identity": document(identity={"accepted": [" fixture"]}),
            "missing web": dict(
                DOCUMENT,
                device={k: v for k, v in DOCUMENT["device"].items() if k != "web"},
            ),
            "missing column": document(device={"web": {"fallback": "x"}}),
            "bad column": document(lighting={"column": "../lighting"}),
            "fallback repeats column": document(
                lighting={"column": "lighting", "fallback": "lighting"}
            ),
            "bad description": document(lighting={"description": 5}),
            "sdk description": document(
                device={"web": {"column": "capture_device", "description": "x"}}
            ),
            "column not read": document(
                device={"accepted": {"phone": {"capture_devce": ["x"]}}}
            ),
            "spelling twice": document(
                device={
                    "accepted": {
                        "a": {"capture_device": ["X1"]},
                        "b": {"capture_device": ["X1"]},
                    }
                }
            ),
            "spelling is a name": document(
                device={"accepted": {**accepted, "a": {SENSOR: ["iphone_13"]}}}
            ),
            "no devices": document(device={"accepted": {}}),
        }
        for label, value in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                naming.Naming(value)

    def test_columns_are_separate_namespaces(self):
        """A detected model and a label may share text but name different devices."""
        names = naming.Naming(
            document(
                device={
                    "accepted": {
                        "a": {SENSOR: ["X1"]},
                        "b": {"capture_device": ["X1"]},
                    }
                }
            )
        )
        self.assertEqual(
            (names.device(SENSOR, "X1"), names.device("capture_device", "X1")),
            ("a", "b"),
        )


class StandardizeTests(unittest.TestCase):
    """Report standard values, raw values, columns, and issues per field."""

    def setUp(self):
        """Use the sample naming document."""
        self.names = naming.Naming(document())

    def standardize(self, sdk, row, annotation=None, model=""):
        """Standardize one synthetic CSV row."""
        return self.names.standardize(sdk, row, annotation or {}, model)

    def test_accepted_values_have_no_issues(self):
        """Accepted lighting and identity pass; a detected model maps to its device."""
        result = self.standardize(
            "app",
            {"lighting": "office_dark", "subject": "fixture"},
            model="SM-F946U1",
        )
        self.assertEqual(
            result["device"],
            dict(value="galaxy_z_fold_5", raw="SM-F946U1", source=SENSOR, issue=""),
        )
        self.assertEqual(result["lighting"]["issue"], "")
        self.assertEqual(result["identity"]["issue"], "")

    def test_other_values_are_flagged_not_changed(self):
        """Lighting is never translated; unknown values keep their raw text."""
        result = self.standardize(
            "app", {"lighting": "white", "subject": "stranger"}, model="SM-A556E"
        )
        self.assertEqual(result["lighting"]["value"], "white")
        self.assertIn("not an accepted lighting", result["lighting"]["issue"])
        self.assertIn("not an accepted identity", result["identity"]["issue"])
        self.assertEqual(result["device"]["value"], "SM-A556E")
        self.assertIn(
            "(input_sensor.model) is not an accepted device", result["device"]["issue"]
        )

    def test_missing_values(self):
        """Empty columns are reported as missing with the column name."""
        result = self.standardize("web", {})
        self.assertEqual(result["lighting"]["issue"], "Missing lighting (lighting)")
        self.assertEqual(result["device"]["issue"], "Missing device (capture_device)")
        self.assertEqual(
            self.standardize("unknown", {})["device"]["issue"], "SDK not recognized"
        )

    def test_empty_identity_list_disables_the_check(self):
        """Only a missing identity is flagged when no identities are listed."""
        names = naming.Naming(with_identities([]))
        issue = names.standardize("web", {"subject": "anyone"}, {}, "")["identity"]
        self.assertEqual(issue["issue"], "")

    def test_app_device_reads_label_then_detected_model(self):
        """The App label has priority; an empty label falls back to the sensor model."""
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
                device = self.standardize("app", row, model=model)["device"]
                self.assertEqual((device["value"], device["source"]), (value, column))

    def test_web_device_has_no_fallback(self):
        """Web reads only its column, even when a sensor model is available."""
        device = self.standardize("web", {}, model="SM-F946U1")["device"]
        self.assertEqual(device["issue"], "Missing device (capture_device)")

    def test_other_columns(self):
        """Fields can be read from another column or the collection annotation."""
        names = naming.Naming(
            document(
                lighting={"column": "annotation.lighting"},
                identity={"column": "person"},
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
        self.write(with_identities(["new-person"]), stamp=10**18)
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
        self.assertIn("not an accepted lighting", web["naming"]["lighting"]["issue"])
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
                "not an accepted lighting", event["naming"]["lighting"]["issue"]
            )
            self.assertEqual(event["naming"]["identity"]["issue"], "")
            record = client.request("/api/captures")[1][0]
            self.assertEqual(record["naming"], event["naming"])


if __name__ == "__main__":
    unittest.main()
