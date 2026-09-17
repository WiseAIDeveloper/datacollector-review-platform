"""Exercise single-batch dashboard filtering with disposable API fixtures."""

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from tests.support import asset_path

source = Path(os.environ["REVIEW_SOURCE"])
batch_names = ["alpha", "beta", "empty"]
matrix = [
    dict(
        folder=name,
        lighting="dark",
        sdk="web",
        device="iphone-13",
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
            lighting="dark",
            test_plan_name="colour_print_enhancement_2",
        ),
    )
    for name, count in [("alpha", 1), ("beta", 3)]
    for subject in ["person-a", "person-b"]
    for index in range(count)
]
data = {
    "captures": rows,
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
        data["matrix"] = matrix
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto("http://fixture/coverage.html")
        filters = page.get_by_role("group", name="Batches filter", exact=True)
        all_button = filters.get_by_role("button", name="All", exact=True)
        alpha = filters.get_by_role("button", name="Alpha", exact=True)
        beta = filters.get_by_role("button", name="Beta", exact=True)
        empty = filters.get_by_role("button", name="Empty", exact=True)
        expect(all_button).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".batch")).to_have_count(3)
        expect(page.locator("#summary b")).to_have_text(["6", "4", "3", "1"])

        alpha.click()
        expect(alpha).to_have_attribute("aria-pressed", "true")
        expect(all_button).to_have_attribute("aria-pressed", "false")
        expect(page.locator(".batch h2")).to_have_text(["Alpha"])
        expect(page.locator("#summary b")).to_have_text(["2", "1", "1", "0"])

        toggle = page.locator(".batch-filter-panel > summary")
        expect(toggle).to_have_text("Batches filter")
        toggle.click()
        expect(alpha).not_to_be_visible()
        expect(page.locator(".batch h2")).to_have_text(["Alpha"])
        page.locator("#refresh").click()
        expect(alpha).not_to_be_visible()
        toggle.focus()
        toggle.press("Enter")
        expect(alpha).to_be_visible()
        expect(alpha).to_have_attribute("aria-pressed", "true")

        beta.focus()
        beta.press("Enter")
        expect(beta).to_be_focused()
        expect(beta).to_have_attribute("aria-pressed", "true")
        expect(alpha).to_have_attribute("aria-pressed", "false")
        expect(page.locator(".batch h2")).to_have_text(["Beta"])
        expect(page.locator("#summary b")).to_have_text(["2", "3", "0", "1"])

        page.locator('[data-view="missing"]').click()
        expect(page.locator(".batch")).to_have_count(0)
        expect(page.get_by_text("No batches in this view.", exact=True)).to_be_visible()
        expect(filters.get_by_role("button")).to_have_count(4)
        empty.click()
        expect(page.locator(".batch h2")).to_have_text(["Empty"])
        expect(page.locator("#summary b")).to_have_text(["2", "0", "2", "0"])
        all_button.click()
        expect(page.locator(".batch h2")).to_have_text(["Alpha", "Empty"])
        expect(page.locator("#subject")).to_have_value("person-a")

        page.locator('[data-view="batches"]').click()
        beta.click()
        page.locator("#subject").select_option("person-b")
        expect(beta).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".batch h2")).to_have_text(["Beta"])
        page.locator("#refresh").click()
        expect(page.locator("#subject")).to_have_value("person-b")
        expect(beta).to_have_attribute("aria-pressed", "true")
        expect(page.locator('[data-view="batches"]')).to_have_text("All batches (1)")
        expect(page.locator('[data-view="excess"]')).to_have_text("Excess (1)")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        screenshots = source / "artifacts" / "batch-filter"
        screenshots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshots / f"dashboard-{width}.png"))

        all_button.focus()
        all_button.press("Space")
        expect(all_button).to_be_focused()
        expect(page.locator(".batch")).to_have_count(3)
        beta.click()
        data["matrix"] = [item for item in matrix if item["folder"] != "beta"]
        page.locator("#refresh").click()
        expect(beta).to_have_count(0)
        expect(all_button).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".batch h2")).to_have_text(["Alpha", "Empty"])
        data["matrix"] = []
        page.locator("#refresh").click()
        expect(filters.get_by_role("button")).to_have_count(1)
        expect(all_button).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#summary b")).to_have_text(["0", "0", "0", "0"])
    assert not errors, errors
    browser.close()

print(
    "PASS batch selection, All reset, totals, status/identity filters, refresh, "
    "empty batches, removed selections, keyboard controls, and desktop/mobile layouts."
)
