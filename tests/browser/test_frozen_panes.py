import shutil
import os
from pathlib import Path
from tests.support import asset_path
import json
import urllib.request
from playwright.sync_api import sync_playwright

src = Path(os.environ["REVIEW_SOURCE"])
base = os.environ["VIEWER_URL"]
data = {
    key: json.load(urllib.request.urlopen(base + "/api/" + key))
    for key in ["captures", "matrix", "batches", "quality", "ingestion?limit=100"]
}
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def route(r):
        """Serve synthetic API responses or source assets for the browser scenario."""
        from urllib.parse import urlparse

        u = urlparse(r.request.url)
        if u.path.startswith("/api/"):
            key = u.path[5:] + ("?" + u.query if u.query else "")
            r.fulfill(json=data.get(key, {}))
            return
        name = "index.html" if u.path == "/" else u.path[1:]
        path = asset_path(src, name)
        if path.is_file():
            r.fulfill(
                body=path.read_text(),
                content_type=(
                    "text/css"
                    if name.endswith(".css")
                    else "text/javascript" if name.endswith(".js") else "text/html"
                ),
            )
        else:
            r.fulfill(body="")

    page.route("**/*", route)
    for width in [1440, 390]:
        page.set_viewport_size({"width": width, "height": 1000})
        for name in [
            "coverage.html",
            "index.html",
            "quality.html",
            "ingestion.html",
            "search.html",
        ]:
            page.goto("http://fixture/" + name)
            page.wait_for_timeout(150)
            header = page.locator(".frozen-pane")
            assert header.count() == 1, name
            assert header.bounding_box()["height"] < (150 if width == 1440 else 300), (
                name,
                width,
                header.bounding_box(),
            )
            filters = page.locator(".header-filters")
            if filters.count():
                assert filters.evaluate("node => node.open") == (width > 760)
                if width == 390:
                    action = page.locator(
                        "#execute" if name == "index.html" else "#save-reviews"
                    )
                    assert action.is_visible(), (name, "hidden primary action")
                    filters.locator("summary").click()
                    assert filters.locator("select").first.is_visible()
                    assert filters.evaluate(
                        "node => node.scrollWidth <= node.clientWidth"
                    )
                    filters.locator("summary").click()
                    assert not filters.locator("select").first.is_visible()
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.wait_for_function(
                        "document.querySelector('.header-filters').open"
                    )
                    page.set_viewport_size({"width": width, "height": 1000})
            page.evaluate(
                'document.querySelector("main").style.minHeight="3000px";window.scrollTo(0,700)'
            )
            page.wait_for_timeout(50)
            assert abs(header.bounding_box()["y"]) < 1, (name, width)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (
                name,
                width,
            )
            if name == "coverage.html":
                page.screenshot(path="/tmp/frozen-" + str(width) + ".png")
    assert not errors, errors
    b.close()
print(
    "PASS all five frozen headers: compact height, visible on scroll, desktop/mobile, no horizontal overflow or JavaScript errors."
)
