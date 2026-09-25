"""Verify numbered genuine references with disposable images and captures."""

import tempfile
import unittest
from pathlib import Path

from app.genuine_gallery import GenuineGallery
from tests.support import IMAGE, running_server, write_csv


class GenuineGalleryTests(unittest.TestCase):
    """Check manifest validation and the public gallery contract."""

    def test_numbered_cards_and_images(self):
        """Show collection counts without publishing source paths or session IDs."""
        with running_server(genuine_gallery=True) as client:
            self.assertTrue(client.request("/api/project-mode")[1]["genuine_gallery"])
            status, cards, _ = client.request("/api/genuine")
            self.assertEqual(status, 200)
            self.assertEqual(
                cards,
                [
                    {"number": "1", "count": 1},
                    {"number": "2", "count": 4},
                    {"number": "3", "count": 0},
                ],
            )
            self.assertNotIn("absolute_ori_path", str(cards))
            self.assertEqual(client.request("/api/genuine-image?number=1")[1], IMAGE)
            self.assertEqual(client.request("/api/genuine-image?number=4")[0], 404)
            self.assertEqual(client.request("/genuine.html")[0], 200)
            self.assertEqual(client.request("/genuine_gallery.js")[0], 200)

    def test_gallery_is_optional_and_manifest_is_validated(self):
        """Keep normal mode intact and reject duplicate or missing references."""
        with running_server() as client:
            self.assertFalse(client.request("/api/project-mode")[1]["genuine_gallery"])
            self.assertEqual(client.request("/api/genuine")[0], 404)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "reference.png"
            image.write_bytes(IMAGE)
            manifest = root / "references.csv"
            rows = [
                {"assigned_number": "1", "absolute_ori_path": str(image)},
                {"assigned_number": "1", "absolute_ori_path": str(image)},
            ]
            write_csv(manifest, rows)
            with self.assertRaisesRegex(ValueError, "unique"):
                GenuineGallery(manifest)
            rows[1]["assigned_number"] = "2"
            rows[1]["absolute_ori_path"] = str(root / "missing.png")
            write_csv(manifest, rows)
            with self.assertRaisesRegex(ValueError, "missing"):
                GenuineGallery(manifest)


if __name__ == "__main__":
    unittest.main()
