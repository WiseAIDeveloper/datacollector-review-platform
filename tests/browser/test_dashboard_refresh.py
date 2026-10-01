"""Verify manual dashboard refresh timestamps and preserved state using disposable API fixtures."""

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from tests.support import asset_path, fixture_fields, with_fields

source = Path(os.environ["REVIEW_SOURCE"])
batch_names = ["alpha", "beta", "empty"]
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
    for name, count in [("alpha", 1), ("beta", 3)]
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
    page = browser.new_page(viewport={"width": 1440, "height": 700})
    page.clock.install()
    page.clock.pause_at("2030-01-01T00:00:00")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    requests = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/captures" in request.url else None
        ),
    )
    page.route("**/*", route)
    page.goto("http://fixture/coverage.html")
    expect(page.locator(".batch")).to_have_count(3)
    page.wait_for_function("!loading")
    page.locator("#subject").select_option("person-b")
    page.locator('[data-batch="beta"]').click()
    details = page.locator(".batch > details")
    for item in details.all():
        item.locator("summary").click()
    original = page.locator(".batch").element_handle()

    # Idle time and window focus never fetch data; manual refresh advances the time.
    status = page.locator("#refresh-status")
    expect(status).to_contain_text("Last refreshed at")
    previous_time = status.inner_text()
    request_count = len(requests)
    page.clock.run_for(30000)
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    assert len(requests) == request_count
    expect(status).to_have_text(previous_time)

    # An unchanged manual refresh leaves the DOM intact but records its success.
    page.locator("#refresh").click()
    page.wait_for_function("!loading")
    assert status.inner_text() != previous_time
    assert len(requests) == request_count + 1
    assert original.evaluate("node => node.isConnected")
    assert all(item.evaluate("node => node.open") for item in details.all())

    # Changed data updates totals without losing selections, expansion, or scroll.
    data["captures"].append(dict(data["captures"][-1], key="new-capture"))
    page.locator("#refresh").click()
    page.wait_for_function("!loading")
    expect(page.locator("#subject")).to_have_value("person-b")
    expect(page.locator('[data-batch="beta"]')).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.locator("#summary b")).to_have_text(["2", "4", "0", "2"])
    assert all(item.evaluate("node => node.open") for item in details.all())
    page.evaluate("window.scrollTo(0, 250)")
    scroll = page.evaluate("window.scrollY")
    data["captures"].append(dict(data["captures"][-1], key="auto-capture"))
    page.clock.run_for(30000)
    expect(page.locator("#summary b")).to_have_text(["2", "4", "0", "2"])
    page.locator("#refresh").click()
    expect(page.locator("#summary b")).to_have_text(["2", "5", "0", "3"])
    assert abs(page.evaluate("window.scrollY") - scroll) <= 1
    assert all(item.evaluate("node => node.open") for item in details.all())

    # A failed manual request preserves the last good view and timestamp.
    successful_time = status.inner_text()
    successful_title = status.get_attribute("title")
    page.route("**/api/captures", lambda request: request.fulfill(status=503, json={}))
    page.clock.run_for(3000)
    page.locator("#refresh").click()
    expect(status).to_contain_text("Refresh failed")
    expect(status).to_contain_text(successful_time)
    assert status.get_attribute("title") == successful_title
    expect(page.locator("#summary b")).to_have_text(["2", "5", "0", "3"])
    request_count = len(requests)
    page.clock.run_for(30000)
    assert len(requests) == request_count
    page.unroute("**/api/captures")
    page.locator("#refresh").click()
    page.wait_for_function("!loading")
    assert "Refresh failed" not in status.inner_text()
    assert status.inner_text() != successful_time

    # Repeated manual clicks cannot create overlapping requests.
    pending = []
    page.route("**/api/captures", lambda request: pending.append(request))
    page.locator("#refresh").click()
    page.wait_for_timeout(50)
    assert len(pending) == 1
    pending_time = status.inner_text()
    page.clock.run_for(6000)
    page.locator("#refresh").click()
    assert len(pending) == 1
    expect(status).to_have_text(pending_time)
    pending.pop().fulfill(json=data["captures"])
    page.wait_for_function("!loading")
    page.unroute("**/api/captures")

    # Review drafts and nested metadata survive changed-data refreshes.
    page.locator('[data-view="excess"]').click()
    excess = page.locator(".excess-review")
    excess.locator(":scope > summary").click()
    capture = page.locator(".capture").first
    capture.get_by_role("button", name="Correct metadata", exact=True).click()
    capture.locator("textarea").fill("Keep this draft")
    capture.locator('select[aria-label="Correct capture_env_lighting"]').select_option(
        "office-white"
    )
    capture.locator("details").first.locator("summary").click()
    capture.locator("textarea").focus()
    draft = capture.locator("textarea").element_handle()
    data["captures"].append(dict(data["captures"][-1], key="during-edit"))
    page.clock.run_for(3000)
    assert draft.evaluate("node => node === document.activeElement")
    expect(page.locator("#summary b")).to_have_text(["2", "5", "0", "3"])
    page.locator("#refresh").click()
    expect(page.locator("#summary b")).to_have_text(["2", "6", "0", "4"])
    expect(capture.locator("textarea")).to_have_value("Keep this draft")
    expect(
        capture.locator('select[aria-label="Correct capture_env_lighting"]')
    ).to_have_value("office-white")
    assert excess.evaluate("node => node.open")
    assert capture.locator("details").first.evaluate("node => node.open")
    assert page.url.endswith("#excess")
    assert not errors, errors
    browser.close()
print(
    "Manual refresh preserves state, records successful refresh times, and never polls."
)
