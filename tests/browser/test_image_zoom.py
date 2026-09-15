import shutil
import os
from pathlib import Path
from tests.support import asset_path
from playwright.sync_api import sync_playwright

src = Path(os.environ["REVIEW_SOURCE"])
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = b.new_page(viewport={"width": 1200, "height": 900})
    page.set_content(
        "<dialog id=\"zoom\"><button id=\"close\">Close</button><img alt=\"fixture\" src=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='400'%3E%3Crect width='600' height='400' fill='green'/%3E%3C/svg%3E\"></dialog>"
    )
    page.add_script_tag(content=asset_path(src, "image_zoom.js").read_text())
    page.evaluate('document.getElementById("zoom").showModal()')
    page.wait_for_function('document.querySelector("img").naturalWidth>0')
    viewport = page.locator(".zoom-viewport")
    viewport.hover()
    page.mouse.wheel(0, -500)
    page.wait_for_function('Number(document.querySelector("img").dataset.zoom)>1')
    before = page.locator("img").get_attribute("style")
    bounds = viewport.bounding_box()
    page.mouse.move(bounds["x"] + 100, bounds["y"] + 100)
    page.mouse.down()
    page.mouse.move(bounds["x"] + 160, bounds["y"] + 140)
    page.mouse.up()
    assert page.locator("img").get_attribute("style") != before
    page.mouse.wheel(0, 10000)
    page.wait_for_function('document.querySelector("img").dataset.zoom==="1"')
    page.mouse.wheel(0, -10000)
    page.wait_for_function('document.querySelector("img").dataset.zoom==="8"')
    page.get_by_role("button", name="Reset image zoom").click()
    assert page.locator("img").get_attribute("data-zoom") == "1"
    page.evaluate(
        'document.getElementById("zoom").close();document.getElementById("zoom").showModal()'
    )
    assert page.locator("img").get_attribute("data-zoom") == "1"
    for name in ["quality.html", "index.html", "coverage.html"]:
        assert 'src="/image_zoom.js"' in asset_path(src, name).read_text()
    b.close()
print(
    "PASS wheel zoom in/out, 100–800% bounds, drag pan, reset, reopen reset, all three review pages wired."
)
