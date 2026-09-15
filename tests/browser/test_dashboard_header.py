import shutil
import os
from pathlib import Path
import json
import urllib.request
from playwright.sync_api import sync_playwright, expect

src = Path(os.environ["REVIEW_SOURCE"])
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    for api in ["captures", "matrix", "batches", "quality"]:
        data = json.load(
            urllib.request.urlopen(os.environ["VIEWER_URL"] + "/api/" + api)
        )
        page.route("**/api/" + api, lambda r, request, data=data: r.fulfill(json=data))
    page.route(
        "**/image_zoom.js",
        lambda r: r.fulfill(
            body=(src / "image_zoom.js").read_text(), content_type="text/javascript"
        ),
    )
    page.route(
        "**/coverage.html",
        lambda r: r.fulfill(
            body=(src / "coverage.html").read_text(), content_type="text/html"
        ),
    )
    page.route(
        "**/terminal.css",
        lambda r: r.fulfill(
            body=(src / "terminal.css").read_text(), content_type="text/css"
        ),
    )
    for width in [1440, 390]:
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto(os.environ["VIEWER_URL"] + "/coverage.html")
        page.locator(".batch").first.wait_for()
        expect(page.locator("#execute")).to_have_count(1)
        button = page.locator("#execute").bounding_box()
        header = page.locator(".dashboard-header").bounding_box()
        assert header["x"] <= button["x"]
        assert button["x"] + button["width"] <= header["x"] + header["width"]
        assert header["y"] <= button["y"]
        assert button["y"] + button["height"] <= header["y"] + header["height"]
        page.evaluate(
            'document.querySelector("main").style.minHeight="3000px";window.scrollTo(0,800)'
        )
        page.wait_for_timeout(150)
        assert abs(page.locator(".dashboard-header").bounding_box()["y"]) < 1
        expect(page.locator("#execute")).to_be_in_viewport()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path="/tmp/dashboard-header-" + str(width) + ".png")
    assert not errors, errors
    b.close()
print(
    "PASS Execute remains inside the sticky header and visible at desktop/mobile widths without overflow."
)
