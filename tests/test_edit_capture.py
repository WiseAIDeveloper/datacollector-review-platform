from tests import support  # Select the requested original or current source.
import csv
import tempfile
import unittest
from pathlib import Path

edit_capture = support.load_application("edit_capture").edit_capture
Conflict = support.load_application("edit_capture").Conflict
INDEXES = support.INDEXES


class EditTests(unittest.TestCase):
    def setUp(self):
        """Create disposable fixtures for this test."""
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "genuine"
        self.folder.mkdir()
        self.row = dict(
            uuid="one",
            filename="one.jpg",
            subject="person",
            lighting="dark",
            capture_device="iphone-13",
        )
        for name in INDEXES:
            support.write_csv(
                self.folder / name,
                [self.row, dict(self.row, uuid="two", filename="two.jpg")],
            )
        (self.folder / "one.jpg").write_bytes(b"image")
        (self.folder / "one.json").write_text("{}")

    def tearDown(self):
        """Close fixture resources and remove temporary files."""
        self.tmp.cleanup()

    def test_both_indexes_and_preserved_files(self):
        """Verify both indexes and preserved files."""
        edit_capture(
            self.root,
            "genuine",
            "one",
            "one.jpg",
            {"lighting": "office-white"},
            self.row,
        )
        for name in INDEXES:
            with (self.folder / name).open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["lighting"] for r in rows], ["office-white", "dark"])
        self.assertEqual((self.folder / "one.jpg").read_bytes(), b"image")
        self.assertEqual((self.folder / "one.json").read_text(), "{}")

    def test_secondary_index_without_filename(self):
        """Verify secondary index without filename."""
        fields = ["uuid", "ori_path", "ocr_path", "fraud_type", "batch_name"]
        support.write_csv(
            self.folder / INDEXES[1],
            [
                dict(
                    uuid="one",
                    ori_path="mykadfront/orig/one.jpg",
                    ocr_path="mykadfront/crop/one.png",
                    fraud_type="recapture",
                    batch_name="genuine",
                )
            ],
            fields=fields,
        )
        edit_capture(
            self.root,
            "genuine",
            "one",
            "one.jpg",
            {"lighting": "office-yellow"},
            self.row,
        )
        with (self.folder / INDEXES[1]).open() as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row["lighting"], "office-yellow")
        self.assertNotIn("filename", row)

    def test_stale_metadata_rejected(self):
        """Verify stale metadata rejected."""
        with self.assertRaises(Conflict):
            edit_capture(
                self.root,
                "genuine",
                "one",
                "one.jpg",
                {"lighting": "office-white"},
                dict(self.row, lighting="office-yellow"),
            )

    def test_protected_fields_and_bad_values(self):
        """Verify protected fields and bad values."""
        for change in [
            {"ori_path": "elsewhere"},
            {"lighting": "invalid"},
            {"subject": ""},
        ]:
            with self.assertRaises(ValueError):
                edit_capture(self.root, "genuine", "one", "one.jpg", change, self.row)

    def test_missing_second_index_no_partial_edit(self):
        """Verify missing second index no partial edit."""
        before = (self.folder / INDEXES[0]).read_bytes()
        (self.folder / INDEXES[1]).unlink()
        with self.assertRaises(FileNotFoundError):
            edit_capture(
                self.root,
                "genuine",
                "one",
                "one.jpg",
                {"lighting": "office-white"},
                self.row,
            )
        self.assertEqual((self.folder / INDEXES[0]).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
