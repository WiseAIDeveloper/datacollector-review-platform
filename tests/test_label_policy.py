"""Regression coverage for the MyKad26 collection label contract."""
import unittest
from app.captures.label_policy import batch_label, normalize_attributes, validate_label


class LabelPolicyTests(unittest.TestCase):
    """Check genuine defaults, fraud batches, and explicit conflicts."""

    def test_missing_form_label_uses_genuine_batch(self):
        """The app/web batch-only forms must produce a genuine label."""
        batch = '002_Genuine_Internal_None_ColouredGhost_003'
        attributes = {'batch': batch}
        self.assertEqual(normalize_attributes(attributes, batch)['fraud_type'], 'genuine')
        validate_label(batch, attributes, require=True)

    def test_all_recapture_attack_types(self):
        """Print and replay batch types remain fraud targets."""
        for attack in ('PrintBW', 'PrintColor', 'PrintCutBW', 'PrintCutColor',
                       'ReplayMobile', 'ReplayMonitor', 'ReplayTablet',
                       'ReplayFrameless', 'Mobile', 'Monitor'):
            self.assertEqual(batch_label(f'002_{attack}_Internal_None_None_001'), 'recapture')

    def test_conflicting_or_missing_export_labels_fail(self):
        """Exports must reject blank labels and either spelling of a contradiction."""
        batch = '002_Genuine_Internal_None_None_001'
        for row in ({}, {'fraud_type': ''}, {'fraud_type': 'recapture'}, {'fraudType': 'recapture'}):
            with self.assertRaises(ValueError):
                validate_label(batch, row, require=True)
        with self.assertRaises(ValueError):
            normalize_attributes({'fraud_type': 'genuine'}, '002_ReplayMobile_Internal_None_None_001')

    def test_unknown_002_attack_fails(self):
        """New 002 classes require an explicit mapping instead of a fraud fallback."""
        with self.assertRaises(ValueError):
            batch_label('002_Unknown_Internal_None_None_001')

    def test_other_projects_are_unaffected(self):
        """The MyKad26 policy must not reinterpret other project labels."""
        row = {'fraud_type': 'tamper'}
        self.assertEqual(normalize_attributes(row.copy(), 'V1_tamper'), row)
        self.assertIsNone(batch_label('legacy_batch'))


if __name__ == '__main__':
    unittest.main()


class ReviewLabelTests(unittest.TestCase):
    """Verify review diagnostics and edit rejection against disposable metadata."""

    def test_conflict_is_visible_and_edit_is_rejected(self):
        """A genuine row labelled fraud must be flagged without modifying indexes."""
        import tempfile
        from pathlib import Path
        from app.captures.catalog import capture_record
        from app.captures.editing import prepare_edit
        from app.captures.naming import Naming
        from tests.support import NAMING, write_csv
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / '002_Genuine_Internal_None_None_001'
            folder.mkdir()
            row = dict(uuid='one', filename='one.jpg', fraud_type='recapture',
                       subject='fixture', capture_device='iphone-13')
            path = folder / 'index_annotation_.csv'
            write_csv(path, [row])
            before = path.read_bytes()
            result = capture_record(folder, 2, row, Naming(NAMING))
            self.assertIn('conflicts', result['label_issue'])
            with self.assertRaises(ValueError):
                prepare_edit(path, folder, 'one', 'one.jpg', {}, row)
            self.assertEqual(path.read_bytes(), before)
