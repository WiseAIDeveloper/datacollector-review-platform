"""Check project audits without reading live captures or changing project definitions."""

import unittest

from app.captures.naming import Naming
from scripts.audit_project_devices import audit

NAMING = Naming(
    {
        "subject": {"role": "identity", "accepted": []},
        "capture_env_lighting": {"accepted": ["office_dark"]},
        "capture_device": {
            "role": "device",
            "app": {"column": "input_sensor.model"},
            "web": {"column": "capture_device"},
            "accepted": {
                "galaxy": {"input_sensor.model": ["SM-1"]},
                "samsung-galaxy-z-fold-5": {},
                "phone": {},
            },
        },
        "replay_device": {"accepted": ["galaxy"]},
    }
)


def capture(folder="batch", sdk="web", naming=None, **fields):
    """Build a catalog-like capture record with its field values."""
    return {"folder": folder, "sdk": sdk, "fields": fields, "naming": naming or {}}


class ProjectAuditTests(unittest.TestCase):
    """Catch mismatches between collector names and generated project requirements."""

    def test_collector_name_drift_and_definition_mismatch(self):
        """Old matrix labels cannot silently match different collector labels."""
        project = {
            "matrix": [
                {"folder": "batch", "sdk": "web", "capture_device": "samsung-fold"}
            ],
            "batches": [
                {
                    "batch_name": "batch",
                    "expected_capture_device": "samsung-galaxy-z-fold-5",
                }
            ],
        }
        captures = [capture(capture_device="samsung-galaxy-z-fold-5")] * 2
        result = audit(project, captures, NAMING)
        self.assertEqual(result["unplanned_captures"][0]["captures"], 2)
        self.assertEqual(
            result["definition_errors"][0],
            dict(
                batch="batch",
                field="capture_device",
                only_in_batches=["samsung-galaxy-z-fold-5"],
                only_in_matrix=["samsung-fold"],
            ),
        )
        project["matrix"][0]["capture_device"] = "samsung-galaxy-z-fold-5"
        result = audit(project, captures, NAMING)
        self.assertFalse(any(result.values()))

    def test_sdk_is_part_of_matching(self):
        """A Web requirement cannot satisfy an App capture with the same device."""
        project = {
            "matrix": [{"folder": "batch", "sdk": "web", "capture_device": "phone"}],
            "batches": [{"batch_name": "batch"}],
        }
        result = audit(project, [capture(sdk="app", capture_device="phone")], NAMING)
        self.assertEqual(result["unplanned_captures"][0]["sdk"], "app")

    def test_only_planned_fields_are_matched(self):
        """Fields the matrix does not plan, like an unused replay device, are ignored."""
        project = {
            "matrix": [
                {
                    "folder": "batch",
                    "sdk": "web",
                    "capture_device": "phone",
                    "capture_env_lighting": "office_dark",
                }
            ],
            "batches": [{"batch_name": "batch"}],
        }
        planned = capture(
            capture_device="phone",
            capture_env_lighting="office_dark",
            replay_device="",
        )
        self.assertEqual(audit(project, [planned], NAMING)["unplanned_captures"], [])
        project["matrix"][0]["replay_device"] = "galaxy"
        self.assertEqual(
            audit(project, [planned], NAMING)["unplanned_captures"][0]["replay_device"],
            "",
        )

    def test_naming_issues_and_nonstandard_plan_values(self):
        """Group capture naming issues and flag plan values outside the naming file."""
        project = {
            "matrix": [
                {
                    "folder": "b",
                    "sdk": "app",
                    "capture_device": "galaxy",
                    "capture_env_lighting": "dark",
                }
            ],
            "batches": [{"batch_name": "b"}],
        }
        issue = dict(raw="dark", issue="dark is not an accepted capture_env_lighting")
        record = capture(
            "b",
            "app",
            {
                "capture_env_lighting": issue,
                "capture_device": dict(raw="SM-1", issue=""),
            },
            capture_device="galaxy",
            capture_env_lighting="dark",
        )
        result = audit(project, [record] * 3, NAMING)
        self.assertEqual(
            result["naming_issues"],
            [dict(field="capture_env_lighting", sdk="app", captures=3, **issue)],
        )
        self.assertEqual(
            result["nonstandard_plan_values"],
            [dict(batch="b", field="capture_env_lighting", value="dark")],
        )


class CollectorOptionsTests(unittest.TestCase):
    """Collector plans may offer any subset of fields, but only standard values."""

    def test_options_must_be_standard_names(self):
        """Direct lists and $ref form files are both checked; other fields are not."""
        import json
        import tempfile
        from pathlib import Path

        from scripts.audit_project_devices import options_report

        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            options = folder / "plan_options.json"
            options.write_text(
                json.dumps(
                    {
                        "subject": [{"display": "A", "value": "anyone"}],
                        "capture_env_lighting": [
                            {"display": "Dark", "value": "office_dark"},
                            {"display": "Other", "value": "other"},
                        ],
                        "batch": [{"display": "B", "value": "not-a-field"}],
                    }
                )
            )
            form = folder / "plan_web.json"
            form.write_text(
                json.dumps(
                    {
                        "display_order": {"1": "capture_device"},
                        "capture_device": {
                            "field_name": "capture_device",
                            "options": {"$ref": "devices.json#/capture_device"},
                        },
                    }
                )
            )
            (folder / "devices.json").write_text(
                json.dumps(
                    {
                        "capture_device": [
                            {"value": "phone"},
                            {"value": "SM-1"},
                        ]
                    }
                )
            )
            self.assertEqual(
                options_report([options, form], NAMING),
                [
                    dict(
                        file="plan_options.json",
                        field="capture_env_lighting",
                        value="other",
                    ),
                    dict(file="plan_web.json", field="capture_device", value="SM-1"),
                ],
            )
