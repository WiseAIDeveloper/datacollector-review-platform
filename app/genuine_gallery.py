"""Load numbered genuine references for the collection status gallery."""

import csv
import mimetypes
from pathlib import Path


class GenuineGallery:
    """Keep reference paths server-side and expose only assigned numbers."""

    def __init__(self, csv_path):
        """Read a fixed numbered manifest without copying genuine images."""
        self.csv_path = Path(csv_path).resolve()
        with self.csv_path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not {"assigned_number", "absolute_ori_path"}.issubset(
                reader.fieldnames or []
            ):
                raise ValueError(
                    "Genuine manifest needs assigned_number and absolute_ori_path"
                )
            rows = list(reader)
        if not rows or len(rows) > 10000:
            raise ValueError("Genuine manifest must contain 1–10,000 rows")
        self.images = {}
        for row in rows:
            number = row["assigned_number"].strip()
            raw_path = Path(row["absolute_ori_path"])
            if not number.isascii() or not number.isdigit() or int(number) < 1:
                raise ValueError("Genuine numbers must be positive integers")
            if number in self.images or not raw_path.is_absolute():
                raise ValueError(
                    "Genuine numbers must be unique with absolute image paths"
                )
            path = raw_path.resolve()
            kind = mimetypes.guess_type(path.name)[0]
            if not path.is_file() or kind not in {
                "image/jpeg",
                "image/png",
                "image/webp",
            }:
                raise ValueError("Genuine reference image is missing or unsupported")
            self.images[number] = (path, kind)

    def cards(self, captures):
        """Count captures by their entered subject without exposing source metadata."""
        counts = {number: 0 for number in self.images}
        for row in captures:
            number = row["metadata"].get("subject", "")
            if number in counts:
                counts[number] += 1
        return [
            {"number": number, "count": counts[number]}
            for number in sorted(self.images, key=lambda value: int(value))
        ]

    def image(self, number):
        """Resolve only numbers present in the configured manifest."""
        return self.images.get(number)
