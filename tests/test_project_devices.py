"""Check device audits without reading live captures or changing project definitions."""

import unittest

from app.captures.naming import Naming
from scripts.audit_project_devices import audit


class ProjectDeviceTests(unittest.TestCase):
    """Catch mismatches between collector names and generated project requirements."""

    def test_collector_name_drift_and_definition_mismatch(self):
        """Legacy matrix labels cannot silently match different collector labels."""
        project = {
            "matrix": [{"folder": "batch", "sdk": "web", "device": "samsung-fold"}],
            "batches": [
                {
                    "batch_name": "batch",
                    "expected_web_devices": "samsung-galaxy-z-fold-5",
                }
            ],
        }
        captures = [
            {"folder": "batch", "sdk": "web", "device": "samsung-galaxy-z-fold-5"}
        ] * 2
        result = audit(project, captures)
        self.assertEqual(result["unmatched_devices"][0]["captures"], 2)
        self.assertEqual(
            result["definition_errors"][0]["only_in_matrix"], ["samsung-fold"]
        )
        project["matrix"][0]["device"] = "samsung-galaxy-z-fold-5"
        self.assertEqual(
            audit(project, captures), {"definition_errors": [], "unmatched_devices": []}
        )

    def test_sdk_is_part_of_device_matching(self):
        """A Web requirement cannot satisfy an App capture with the same device label."""
        project = {
            "matrix": [{"folder": "batch", "sdk": "web", "device": "phone"}],
            "batches": [{"batch_name": "batch"}],
        }
        captures = [{"folder": "batch", "sdk": "app", "device": "phone"}]
        self.assertEqual(audit(project, captures)["unmatched_devices"][0]["sdk"], "app")

    def test_naming_issues_and_nonstandard_plan_values(self):
        """Group capture naming issues and flag plan values outside the naming file."""
        naming = Naming(
            {
                "sources": {
                    "lighting": {"field": "lighting"},
                    "identity": {"field": "subject"},
                    "app_device": {"field": "input_sensor.model"},
                    "web_device": {"field": "capture_device"},
                },
                "lighting": ["office_dark"],
                "devices": {"galaxy": {"app": ["SM-1"]}},
            }
        )
        project = {
            "matrix": [
                {"folder": "b", "sdk": "app", "device": "galaxy", "lighting": "dark"}
            ],
            "batches": [{"batch_name": "b"}],
        }
        issue = dict(raw="dark", issue="dark is not a standard lighting name")
        capture = {
            "folder": "b",
            "sdk": "app",
            "device": "galaxy",
            "naming": {"lighting": issue, "device": dict(raw="SM-1", issue="")},
        }
        result = audit(project, [capture] * 3, naming)
        self.assertEqual(
            result["naming_issues"],
            [dict(field="lighting", sdk="app", captures=3, **issue)],
        )
        self.assertEqual(
            result["nonstandard_plan_values"],
            [dict(batch="b", field="lighting", value="dark")],
        )
