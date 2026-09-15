"""Live read checks and mocked mutations: no real capture edits or deletions."""

import shutil
import os


import json
import urllib.request
from playwright.sync_api import sync_playwright, expect

BASE = os.environ["VIEWER_URL"]
with urllib.request.urlopen(BASE + "/api/captures") as response:
    row = json.load(response)[0]
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    errors = []
    writes = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/search.html")
    page.locator("#query").fill(row["metadata"]["uuid"])
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.locator("#results")).to_contain_text(row["metadata"]["filename"])
    page.locator("#results button").first.click()
    expect(page.locator("#review")).to_be_visible()
    page.locator("#edit-lighting").wait_for()
    page.wait_for_function('document.getElementById("review-image").naturalWidth>0')
    page.route("**/api/capture?*", lambda r: r.fulfill(json=row))

    def save(route):
        """Record a mocked metadata edit and update the synthetic response."""
        payload = route.request.post_data_json
        writes.append(payload)
        row["metadata"].update(payload["changes"])
        route.fulfill(json={"updated": True})

    page.route("**/api/edit-capture", save)
    page.route(
        "**/api/apply-decisions",
        lambda r: (
            writes.append(r.request.post_data_json),
            r.fulfill(json={"deleted": 1}),
        ),
    )
    new_light = (
        "office-yellow"
        if row["metadata"].get("lighting") != "office-yellow"
        else "dark"
    )
    page.locator("#edit-lighting").select_option(new_light)
    page.once("dialog", lambda d: d.dismiss())
    page.locator("#save-metadata").click()
    assert not writes

    def confirm(d):
        """Confirm a mocked edit or deletion without writing to the dataset."""
        d.accept("fixture-pin") if d.type == "prompt" else d.accept()

    page.on("dialog", confirm)
    page.locator("#save-metadata").click()
    expect(page.locator("#edit-lighting")).to_have_value(new_light)
    page.wait_for_function("!editing")
    assert writes[0]["changes"] == {"lighting": new_light}
    page.locator("#remove-capture").click()
    expect(page.locator("#review")).not_to_be_visible()
    assert writes[-1]["confirm_count"] == 1
    page.goto(BASE + "/ingestion.html")
    page.locator("#logs button").first.wait_for()
    assert "Test plan" not in page.locator("th").all_text_contents()
    page.locator("#logs button").first.click()
    expect(page.locator("#review")).to_be_visible()
    page.locator("#edit-subject").wait_for()
    assert not errors, errors
    browser.close()
print(
    "PASS image-ID search, image loading, cancel without writes, save/delete UI with mocked writes, ingestion Edit, removed Test plan column."
)
