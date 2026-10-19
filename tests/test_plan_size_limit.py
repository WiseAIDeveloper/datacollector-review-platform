"""Keep expanded colour matrices readable through upload and folder discovery."""
import tempfile
import unittest
from pathlib import Path
from app.projects import parse_csv, validate_pair, MATRIX_FIELDS, BATCH_FIELDS
from app.folder_projects import FolderProjects
from tests.support import running_server

class PlanSizeLimitTests(unittest.TestCase):
    """Exercise realistic multirow CSVs beyond the former upload-body ceiling."""
    def test_large_matrix_upload_and_folder_discovery(self):
        """Accept the same large plan through both supported loading paths."""
        matrix = 'matrix_name,folder,sdk,expected_count_per_identity,capture_device\n' + ''.join(
            f'plan,genuine,app,2,device_{i}_' + 'x' * 3000 + '\n' for i in range(2500)
        )
        batches = 'batch_name,test_plan_name\ngenuine,plan\n'
        self.assertGreater(len(matrix.encode()), 5_000_000)
        self.assertLess(len(matrix.encode()), 10_000_000)
        plan = parse_csv(matrix, MATRIX_FIELDS, 'Test plan')
        definitions = parse_csv(batches, BATCH_FIELDS, 'Batches')
        self.assertEqual(validate_pair(plan, definitions), 'plan')
        with running_server() as client:
            status, project, _ = client.request('/api/projects', {
                'name': 'Expanded plan', 'matrix_csv': matrix, 'batches_csv': batches,
            })
            self.assertEqual(status, 200)
            status, saved, _ = client.request('/api/project?project=' + project['id'])
            self.assertEqual(status, 200)
            self.assertEqual(len(saved['matrix']), 2500)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'expanded'
            folder.mkdir()
            (folder / 'plan.csv').write_text(matrix)
            (folder / 'plan_batches.csv').write_text(batches)
            projects = FolderProjects(root, root)
            self.assertEqual(len(projects.get('expanded')['matrix']), 2500)
            (folder / 'plan.csv').write_text(matrix + ' ' * 10_000_000)
            with self.assertRaisesRegex(ValueError, '10 MB'):
                projects.get('expanded')
        with self.assertRaisesRegex(ValueError, '10 MB'):
            parse_csv(matrix + ' ' * 10_000_000, MATRIX_FIELDS, 'Test plan')
