"""Validate the naming file's fields and their effect on records, edits, and APIs."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.support import INDEXES, dataset, running_server, write_csv

from app.captures import catalog, naming
from app.captures.editing import Conflict, edit_capture

SENSOR = "input_sensor.model"
DOCUMENT = {
    "subject": {"role": "identity", "accepted": ["fixture", "another"]},
    "capture_env_lighting": {
        "description": "Lighting chosen in the collector",
        "required": True,
        "accepted": ["office_white", "office_yellow", "office_dark", "random_bg"],
    },
    "capture_device": {
        "role": "device",
        "description": "Phone used for the capture",
        "app": {"column": "capture_device", "fallback": SENSOR},
        "web": {"column": "capture_device"},
        "accepted": {
            "galaxy_z_fold_5": {SENSOR: ["SM-F946U1"]},
            "iphone_13": {"capture_device": ["iphone-13"]},
        },
    },
    "replay_device": {
        "accepted": {"galaxy_z_fold_5": ["samsung-galaxy-z-fold-5"], "iphone_14": []}
    },
    "user": {},
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


class NamingDocumentTests(unittest.TestCase):
    """Reject naming files that would be ambiguous or silently misread."""

    def test_fields_in_order(self):
        """Every block is a field; its name is its column unless it says otherwise."""
        names = naming.Naming(document())
        self.assertEqual(
            [field.key for field in names.fields],
            [
                "subject",
                "capture_env_lighting",
                "capture_device",
                "replay_device",
                "user",
            ],
        )
        self.assertEqual(
            (names.identity.key, names.device.key), ("subject", "capture_device")
        )
        self.assertEqual(
            [field.key for field in names.dimensions],
            ["capture_env_lighting", "replay_device", "user"],
        )
        self.assertEqual(
            names.field("capture_env_lighting").columns, ("capture_env_lighting",)
        )
        self.assertEqual(
            names.device.sdk_columns,
            {"app": ("capture_device", SENSOR), "web": ("capture_device",)},
        )
        self.assertEqual(
            set(names.editable()),
            {
                "subject",
                "capture_env_lighting",
                "capture_device",
                "replay_device",
                "user",
            },
        )
        described = {field["key"]: field for field in names.describe()}
        self.assertEqual(described["user"]["accepted"], None)
        self.assertEqual(
            described["capture_env_lighting"]["description"],
            "Lighting chosen in the collector",
        )

    def test_invalid_documents(self):
        """Missing roles, unknown keys, duplicates, and conflicting spellings fail."""
        cases = {
            "empty": {},
            "no identity": document(subject=None),
            "no device": document(capture_device=None),
            "two identities": document(user={"role": "identity", "accepted": []}),
            "unknown role": document(user={"role": "person"}),
            "unknown key": document(capture_env_lighting={"values": []}),
            "label key": document(user={"label": "User"}),
            "empty list": document(capture_env_lighting={"accepted": []}),
            "duplicate": document(capture_env_lighting={"accepted": ["a", "a"]}),
            "untrimmed identity": document(subject={"accepted": [" fixture"]}),
            "bad column": document(capture_env_lighting={"column": "../x"}),
            "fallback repeats": document(
                capture_env_lighting={"fallback": "capture_env_lighting"}
            ),
            "bad required": document(user={"required": "yes"}),
            "missing web": document(capture_device={"web": None}),
            "column not read": document(
                capture_device={"accepted": {"phone": {"capture_devce": ["x"]}}}
            ),
            "device spelling twice": document(
                capture_device={
                    "accepted": {
                        "a": {"capture_device": ["X1"]},
                        "b": {"capture_device": ["X1"]},
                    }
                }
            ),
            "spelling is a name": document(
                replay_device={"accepted": {"a": ["b"], "b": []}}
            ),
            "same column twice": document(user={"column": "subject"}),
            "bad field name": dict(document(), **{"bad name": {}}),
        }
        for label, value in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                naming.Naming(value)

    def test_device_columns_are_separate_namespaces(self):
        """A detected model and a label may share text but name different devices."""
        names = naming.Naming(
            document(
                capture_device={
                    "accepted": {
                        "a": {SENSOR: ["X1"]},
                        "b": {"capture_device": ["X1"]},
                    }
                }
            )
        )
        self.assertEqual(
            (
                names.device.standard(SENSOR, "X1"),
                names.device.standard("capture_device", "X1"),
            ),
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
        """Accepted values pass; a detected model maps to its device."""
        result = self.standardize(
            "app",
            {"capture_env_lighting": "office_dark", "subject": "fixture"},
            model="SM-F946U1",
        )
        self.assertEqual(
            result["capture_device"],
            dict(value="galaxy_z_fold_5", raw="SM-F946U1", source=SENSOR, issue=""),
        )
        self.assertFalse(any(v["issue"] for v in result.values()))

    def test_other_values_are_flagged_not_changed(self):
        """Unknown values keep their raw text and name the field."""
        result = self.standardize(
            "app",
            {"capture_env_lighting": "white", "subject": "stranger"},
            model="SM-A556E",
        )
        self.assertEqual(result["capture_env_lighting"]["value"], "white")
        self.assertEqual(
            result["capture_env_lighting"]["issue"],
            "white is not an accepted capture_env_lighting",
        )
        self.assertIn("not an accepted subject", result["subject"]["issue"])
        self.assertIn(
            "(input_sensor.model) is not an accepted capture_device",
            result["capture_device"]["issue"],
        )

    def test_missing_values(self):
        """Required fields report their column; optional ones may be empty."""
        result = self.standardize("web", {})
        self.assertEqual(
            result["capture_env_lighting"]["issue"],
            "Missing capture_env_lighting (capture_env_lighting)",
        )
        self.assertEqual(
            result["capture_device"]["issue"],
            "Missing capture_device (capture_device)",
        )
        self.assertEqual(result["replay_device"]["issue"], "")
        self.assertEqual(result["user"]["issue"], "")
        absent = self.standardize("web", {"replay_device": "na"})["replay_device"]
        self.assertEqual((absent["raw"], absent["value"], absent["issue"]), ("na", "", ""))
        self.assertEqual(
            self.standardize("unknown", {})["capture_device"]["issue"],
            "SDK not recognized",
        )

    def test_spellings_and_free_text(self):
        """Listed spellings map to their standard name; free text is kept as is."""
        result = self.standardize(
            "web",
            {"replay_device": "samsung-galaxy-z-fold-5", "user": "anyone"},
        )
        self.assertEqual(result["replay_device"]["value"], "galaxy_z_fold_5")
        self.assertEqual(
            result["user"], dict(value="anyone", raw="anyone", source="user", issue="")
        )
        self.assertIn(
            "not an accepted replay_device",
            self.standardize("web", {"replay_device": "ipad"})["replay_device"][
                "issue"
            ],
        )

    def test_empty_identity_list_disables_the_check(self):
        """Only a missing identity is flagged when no identities are listed."""
        names = naming.Naming(document(subject={"accepted": []}))
        result = names.standardize("web", {"subject": "anyone"}, {}, "")
        self.assertEqual(result["subject"]["issue"], "")

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
                device = self.standardize("app", row, model=model)["capture_device"]
                self.assertEqual((device["value"], device["source"]), (value, column))

    def test_web_device_has_no_fallback(self):
        """Web reads only its column, even when a sensor model is available."""
        device = self.standardize("web", {}, model="SM-F946U1")["capture_device"]
        self.assertEqual(device["issue"], "Missing capture_device (capture_device)")

    def test_other_columns(self):
        """Fields can be read from another column or the collection annotation."""
        names = naming.Naming(
            document(
                capture_env_lighting={"column": "annotation.lighting"},
                subject={"column": "person"},
            )
        )
        result = names.standardize(
            "web",
            {"person": "another", "capture_device": "iphone-13"},
            {"lighting": "office_white"},
            "",
        )
        self.assertEqual(result["capture_env_lighting"]["value"], "office_white")
        self.assertEqual(
            result["capture_env_lighting"]["source"], "annotation.lighting"
        )
        self.assertEqual(result["subject"]["value"], "another")
        self.assertNotIn("capture_env_lighting", names.editable())


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
        self.write(document(subject={"accepted": ["new-person"]}), stamp=10**18)
        self.assertEqual(names.current().identity.accepted, {"new-person"})
        self.write("{", stamp=2 * 10**18)
        self.assertEqual(names.current().identity.accepted, {"new-person"})
        self.assertIn("not reloaded", names.error)
        self.write(document(), stamp=3 * 10**18)
        self.assertEqual(names.current().identity.accepted, {"fixture", "another"})
        self.assertEqual(names.error, "")


class DatasetTests(unittest.TestCase):
    """Apply the naming file to catalog records and metadata edits."""

    def setUp(self):
        """Create a disposable dataset with one web and one app capture."""
        temporary = tempfile.TemporaryDirectory(prefix="naming-data-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rows = dataset(self.root, count=2)
        self.rows[1].update(capture_device="", input_sensor=FOLD_SENSOR)
        self.rows[1]["capture_env_lighting"] = "office_white"
        write_csv(self.root / "genuine" / INDEXES[0], self.rows)
        self.names = naming.Naming(document())

    def test_records_with_naming(self):
        """Records carry every field by name; nonstandard values carry issues."""
        web, app = catalog.records(self.root, self.names)
        self.assertEqual(
            (web["device"], app["device"]), ("iphone_13", "galaxy_z_fold_5")
        )
        self.assertEqual(app["fields"]["capture_env_lighting"], "office_white")
        self.assertEqual(app["identity"], "fixture")
        self.assertIn(
            "not an accepted capture_env_lighting",
            web["naming"]["capture_env_lighting"]["issue"],
        )
        self.assertEqual(app["naming"]["capture_env_lighting"]["issue"], "")
        self.assertEqual(app["annotation"]["capture_env_lighting"], "office-white")
        self.assertEqual(app["metadata"], self.rows[1])

    def test_edits_require_standard_names(self):
        """Edits reject columns no field reads and values outside the naming file."""
        row = self.rows[0]
        for changes in (
            {"capture_env_lighting": "dark"},
            {"subject": "stranger"},
            {"subject": " "},
            {"capture_device": "iphone-13"},
            {"replay_device": "ipad"},
            {"lighting": "office_dark"},
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
            {
                "capture_env_lighting": "office_dark",
                "capture_device": "iphone_13",
                "replay_device": "",
                "user": "anyone",
            },
            row,
            naming=self.names,
        )
        self.assertTrue(result["updated"])


class ServerTests(unittest.TestCase):
    """Serve fields and naming reports through the APIs."""

    def test_fields_and_ingestion_report_naming_issues(self):
        """The fields API lists the naming file; events carry per-field issues."""
        with running_server(naming=document()) as client:
            fields = client.request("/api/fields")[1]
            self.assertEqual([field["key"] for field in fields], list(DOCUMENT))
            events = client.request("/api/ingestion")[1]["events"]
            self.assertEqual(len(events), 5)
            event = events[0]
            self.assertEqual(event["fields"]["capture_device"], "iphone_13")
            self.assertEqual(event["fields"]["capture_env_lighting"], "dark")
            self.assertIn(
                "not an accepted capture_env_lighting",
                event["naming"]["capture_env_lighting"]["issue"],
            )
            self.assertEqual(event["naming"]["subject"]["issue"], "")
            record = client.request("/api/captures")[1][0]
            self.assertEqual(record["naming"], event["naming"])


if __name__ == "__main__":
    unittest.main()
