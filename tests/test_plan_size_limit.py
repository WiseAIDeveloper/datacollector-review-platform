"""Keep expanded colour matrices readable through upload and folder discovery."""
import tempfile
import unittest
from pathlib import Path
from app.projects import parse_csv, validate_pair, MATRIX_FIELDS, BATCH_FIELDS
from app.folder_projects import FolderProjects

class PlanSizeLimitTests(unittest.TestCase):
    """Exercise realistic multirow CSVs beyond the former 400 KB ceiling."""
    def test_large_matrix_upload_and_folder_discovery(self):
        """Accept the same large plan through both supported loading paths."""
        matrix = 'matrix_name,folder,sdk,expected_count_per_identity,capture_device\n' + ''.join(
            f'plan,genuine,app,2,device_{i}_' + 'x' * 200 + '\n' for i in range(2500)
        )
        batches = 'batch_name,test_plan_name\ngenuine,plan\n'
        self.assertGreater(len(matrix.encode()), 400_000)
        self.assertLess(len(matrix.encode()), 1_000_000)
        plan = parse_csv(matrix, MATRIX_FIELDS, 'Test plan')
        definitions = parse_csv(batches, BATCH_FIELDS, 'Batches')
        self.assertEqual(validate_pair(plan, definitions), 'plan')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'expanded'
            folder.mkdir()
            (folder / 'plan.csv').write_text(matrix)
            (folder / 'plan_batches.csv').write_text(batches)
            projects = FolderProjects(root, root)
            self.assertEqual(len(projects.get('expanded')['matrix']), 2500)
            (folder / 'plan.csv').write_text(matrix + ' ' * 1_000_000)
            with self.assertRaisesRegex(ValueError, '1 MB'):
                projects.get('expanded')
        with self.assertRaisesRegex(ValueError, '1 MB'):
            parse_csv(matrix + ' ' * 1_000_000, MATRIX_FIELDS, 'Test plan')
