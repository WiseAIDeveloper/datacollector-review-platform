"""Check additive collection targets without modifying production plans."""

import json
import subprocess
import unittest
from pathlib import Path

from app.projects import validate_pair


class IdentityTargetTests(unittest.TestCase):
    """Keep overlapping and newly added identities' targets independent."""

    def test_validate_additive_targets(self):
        """Accept mixed targets while retaining the legacy integer count."""
        row = dict(
            matrix_name="plan",
            folder="batch",
            sdk="app",
            expected_count_per_identity="2",
            expected_count_by_subject=json.dumps({"existing": 4, "new": 2}),
        )
        self.assertEqual(validate_pair([row], [{"batch_name": "batch"}]), "plan")
        for value in [
            "bad json",
            "[]",
            "{}",
            '{"existing": -1}',
            '{"existing": true}',
            '{"": 2}',
            '{"existing": 2.5}',
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_pair(
                    [dict(row, expected_count_by_subject=value)],
                    [{"batch_name": "batch"}],
                )

    def test_duplicate_groups_with_different_identity_counts(self):
        """Two count maps must not make the same capture requirement appear twice."""
        row = dict(
            matrix_name="plan",
            folder="batch",
            sdk="app",
            expected_count_per_identity="2",
            expected_count_by_subject='{"existing":4}',
        )
        other = dict(row, expected_count_by_subject='{"new":2}')
        with self.assertRaisesRegex(ValueError, "duplicate capture requirements"):
            validate_pair([row, other], [{"batch_name": "batch"}])

    def test_dashboard_target_selection(self):
        """The browser uses four for repeat identities, two for new, zero for unassigned."""
        script = Path(__file__).resolve().parents[1] / "web/static/js/fields.js"
        source = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
global.window = {};
global.fetch = async () => ({ok: true, json: async () => []});
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  const model = await window.captureFields.load();
  const row = {expected_count_per_identity: '2',
    expected_count_by_subject: JSON.stringify({existing: 4, new: 2})};
  assert.equal(model.expected(row, 'existing'), 4);
  assert.equal(model.expected(row, 'new'), 2);
  assert.equal(model.expected(row, 'unassigned'), 0);
  assert.equal(model.expected({expected_count_per_identity: '2'}, 'existing'), 2);
  assert.equal(model.expected({expected_count_per_identity: '2',
    expected_count_by_subject: ''}, 'existing'), 2);
})().catch(error => {console.error(error); process.exit(1);});
"""
        subprocess.run(["node", "-e", source, str(script)], check=True)
