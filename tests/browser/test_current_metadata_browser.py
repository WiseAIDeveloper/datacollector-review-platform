import shutil
import os
import json
import urllib.request
from playwright.sync_api import sync_playwright, expect

BASE = os.environ["VIEWER_URL"]


def get(path):
    """Read JSON from the isolated fixture server."""
    with urllib.request.urlopen(BASE + path) as r:
        return json.load(r)


rows = get("/api/captures")
state = get("/api/ingestion")
current = {r["key"]: r for r in rows}
for event in state["events"]:
    if event["available"]:
        row = current[event["key"]]
        assert event["fields"] == row["fields"]
        assert event["fields"]["subject"] == row["metadata"].get("subject", "")
print("PASS live ingestion API matches current CSV metadata")
event = next(e for e in state["events"] if e["available"])
row = current[event["key"]]
state["events"] = [event]
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    page.route("**/api/ingestion?*", lambda route: route.fulfill(json=state))
    page.route("**/api/capture?*", lambda route: route.fulfill(json=row))

    def save(route):
        """Record a mocked metadata edit and update the synthetic response."""
        changes = route.request.post_data_json["changes"]
        row["metadata"].update(changes)
        event["fields"].update(changes)
        route.fulfill(json={"updated": True})

    page.route("**/api/edit-capture", save)
    page.goto(BASE + "/ingestion.html")
    page.locator("#logs button").click()
    page.locator("#edit-capture_env_lighting").wait_for()
    capture_env_lighting = (
        "office-white"
        if row["metadata"].get("capture_env_lighting") != "office-white"
        else "dark"
    )
    page.locator("#edit-capture_env_lighting").select_option(capture_env_lighting)
    page.on(
        "dialog", lambda d: d.accept("test-pin") if d.type == "prompt" else d.accept()
    )
    page.locator("#save-metadata").click()
    # Columns: picture, batch, SDK, then fields in naming-file order.
    expect(page.locator("#logs tr").first.locator("td").nth(4)).to_have_text(
        capture_env_lighting
    )
    page.wait_for_function("!editing")
    expect(page.locator("#edit-capture_env_lighting")).to_have_value(
        capture_env_lighting
    )
    browser.close()
print(
    "PASS saving metadata refreshes visible ingestion row (mocked edit, no real changes)"
)
