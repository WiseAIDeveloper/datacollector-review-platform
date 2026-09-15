import shutil
import os

"""Compare original and refactored page rendering using identical synthetic API data."""

import argparse
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from tests.support import PROJECT, running_server


def main():
    """Compare fixture pages, allowing only sparse one-level rasterization rounding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    args = parser.parse_args()
    output = PROJECT / "artifacts/browser-parity"
    output.mkdir(parents=True, exist_ok=True)
    with running_server(args.original) as original, running_server(PROJECT) as current:
        responses = {
            "/api/" + name: original.request("/api/" + name)[1]
            for name in ("captures", "matrix", "batches", "quality", "ingestion")
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("CHROME_PATH")
                or shutil.which("google-chrome"),
                args=["--no-sandbox"],
            )
            try:
                for width in (1440, 390):
                    for route in (
                        "/",
                        "/coverage.html",
                        "/quality.html",
                        "/ingestion.html",
                        "/search.html",
                    ):
                        screenshots = []
                        for label, client in (
                            ("original", original),
                            ("current", current),
                        ):
                            page = browser.new_page(
                                viewport={"width": width, "height": 1000},
                                device_scale_factor=1,
                            )
                            for api, body in responses.items():
                                page.route(
                                    "**" + api + "*",
                                    lambda route, request, body=body: route.fulfill(
                                        json=body
                                    ),
                                )
                            page.goto(client.base + route)
                            page.wait_for_load_state("networkidle")
                            path = (
                                output
                                / f"{route.strip('/') or 'index'}-{width}-{label}.png"
                            )
                            page.screenshot(
                                path=str(path), full_page=True, animations="disabled"
                            )
                            screenshots.append(path)
                            page.close()
                        with Image.open(screenshots[0]) as before, Image.open(
                            screenshots[1]
                        ) as after:
                            assert (
                                before.size == after.size
                            ), f"Page dimensions changed: {route} at {width}"
                            difference = ImageChops.difference(
                                before.convert("RGB"), after.convert("RGB")
                            )
                            changed = sum(any(pixel) for pixel in difference.getdata())
                            max_delta = max(
                                high for low, high in difference.getextrema()
                            )
                            # Chrome can round a few antialiased corner pixels differently between pages.
                            if (
                                max_delta > 1
                                or changed > before.width * before.height * 0.0001
                            ):
                                difference.save(
                                    output
                                    / f"difference-{route.strip('/') or 'index'}-{width}.png"
                                )
                                raise AssertionError(
                                    f"Page rendering changed: {route} at {width}"
                                )
                        print(
                            f"PASS visual parity: {route} at {width}px ({changed} rounding pixels)",
                            flush=True,
                        )
            finally:
                browser.close()


if __name__ == "__main__":
    main()
