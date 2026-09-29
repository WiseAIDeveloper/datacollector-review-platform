"""Identify newest excess captures from current records and plan counts."""

import unittest

from app.ingestion import possible_excess_keys
from tests.test_project_devices import NAMING


def record(key, batch="printed", subject="person"):
    """Build one available capture with a matrix-matching field set."""
    return dict(
        key=key,
        folder=batch,
        sdk="web",
        metadata={"test_plan_name": "plan"},
        fields=dict(subject=subject, capture_env_lighting="office_dark", capture_device="phone"),
    )


class PossibleExcessTests(unittest.TestCase):
    """Only the newest available captures beyond the plan count are excess."""

    def test_counts_per_identity_and_ignores_deleted_events(self):
        """A deleted event and a second identity cannot trigger purple."""
        plan = [
            dict(
                folder=batch,
                sdk="web",
                test_plan_name="plan",
                capture_env_lighting="office_dark",
                capture_device="phone",
                expected_count_per_identity=str(expected),
            )
            for batch, expected in (("printed", 1), ("genuine", 2))
        ]
        captures = [
            record("printed-old"),
            record("printed-new"),
            record("different-person", subject="other"),
            record("genuine-old", "genuine"),
            record("genuine-middle", "genuine"),
            record("genuine-new", "genuine"),
        ]
        newest = [
            "deleted",
            "genuine-new",
            "genuine-middle",
            "genuine-old",
            "different-person",
            "printed-new",
            "printed-old",
        ]
        self.assertEqual(
            possible_excess_keys(captures, plan, NAMING, newest),
            {"printed-new", "genuine-new"},
        )


if __name__ == "__main__":
    unittest.main()
