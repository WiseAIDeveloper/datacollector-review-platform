"""Exercise single-batch dashboard filtering with disposable API fixtures."""

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from tests.support import asset_path, fixture_fields, with_fields

source = Path(os.environ["REVIEW_SOURCE"])
batch_names = ["002_Genuine_Internal_None_001", "002_PrintBW_Internal_None_001", "002_PrintBW_Internal_None_002"]
matrix = [
    dict(
        folder=name,
        capture_env_lighting="dark",
        sdk="web",
        capture_device="iphone-13",
        expected_count_per_identity="2",
    )
    for name in batch_names
]
rows = [
    dict(
        key=f"{name}/{subject}/{index}.jpg",
        folder=name,
        sdk="web",
        device="iphone-13",
        line=index + 2,
        metadata=dict(
            uuid=f"{subject}-{index}",
            filename=f"{index}.jpg",
            subject=subject,
            capture_env_lighting="dark",
            test_plan_name="colour_print_enhancement_2",
        ),
    )
    for name, count in [(batch_names[0], 1), (batch_names[1], 3)]
    for subject in ["person-a", "person-b"]
    for index in range(count)
]
data = {
    "fields": fixture_fields(),
    "captures": with_fields(rows),
    "matrix": matrix,
    "batches": [
        dict(batch_name=name, batch_display_name=name.title(), sort_order=str(i))
        for i, name in enumerate(batch_names)
    ],
    "quality": {},
}


def route(request):
    """Serve application assets and synthetic API responses without live data."""
    path = urlparse(request.request.url).path
    if path.startswith("/api/"):
        request.fulfill(json=data.get(path[5:], {}))
        return
    asset = asset_path(source, path[1:])
    if asset.is_file():
        content_type = (
            "text/css"
            if path.endswith(".css")
            else "text/javascript" if path.endswith(".js") else "text/html"
        )
        request.fulfill(body=asset.read_text(), content_type=content_type)
    else:
        request.fulfill(body="")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/*", route)
    for width in [1440, 390]:
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto("http://fixture/coverage.html")
        select = page.get_by_label("Attack type", exact=True)
        filters = page.get_by_role("group", name="Batches filter", exact=True)
        expect(filters.locator("button")).to_have_count(4)
        select.select_option("PrintBW")
        expect(filters.locator("button")).to_have_count(3)
        expect(filters.get_by_role("button", name=batch_names[0], exact=True)).to_have_count(0)
        expect(page.locator("#batch-content > .batch")).to_have_count(2)
        filters.get_by_role("button", name=batch_names[1], exact=True).click()
        expect(page.locator("#batch-content > .batch")).to_have_count(1)
        select.select_option("Genuine")
        expect(filters.locator("button")).to_have_count(2)
        expect(filters.get_by_role("button", name="All", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#batch-content > .batch")).to_have_count(1)
        page.locator("#subject").select_option("person-b")
        expect(select).to_have_value("Genuine")
        page.get_by_role("button", name="Refresh data", exact=True).click()
        expect(select).to_have_value("Genuine")
        select.select_option("")
        expect(filters.locator("button")).to_have_count(4)
        expect(page.locator("#batch-content > .batch")).to_have_count(3)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    browser.close()
print("Attack-type filtering passed at desktop and mobile widths")
