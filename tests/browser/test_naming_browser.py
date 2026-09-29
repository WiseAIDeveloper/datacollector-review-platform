"""Browser check that nonstandard names are highlighted, using mocked API data only."""

import os
import shutil
from datetime import datetime, timezone

from playwright.sync_api import expect, sync_playwright

BASE = os.environ["VIEWER_URL"]
OK = dict(value="", raw="", source="", issue="")
NAMING = dict(
    capture_env_lighting=dict(
        OK,
        value="white",
        raw="white",
        issue="white is not an accepted capture_env_lighting",
    ),
    subject=dict(OK, value="fixture", raw="fixture"),
    capture_device=dict(
        OK,
        value="SM-A556E",
        raw="SM-A556E",
        source="input_sensor.model",
        issue="SM-A556E (input_sensor.model) is not an accepted capture_device",
    ),
)


def ingestion(request):
    """Serve one ingestion event with capture_env_lighting and device issues."""
    detected = datetime.now(timezone.utc).isoformat()
    event = dict(
        id=1,
        key="batch/u1/flagged.jpg",
        status="ingested",
        detected_at=detected,
        filename="flagged.jpg",
        batch="batch",
        sdk="app",
        fields=dict(
            capture_env_lighting="white", subject="fixture", capture_device="SM-A556E"
        ),
        test_plan="plan",
        creation_time="capture time",
        naming=NAMING,
        available=True,
    )
    request.fulfill(
        json=dict(
            last_scan=detected,
            errors=[],
            pending_images=0,
            total=1,
            existing=0,
            ingested=1,
            events=[event],
            next_before=None,
            actions=[],
            action_total=0,
        )
    )


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    page.route("**/api/ingestion?*", ingestion)
    page.goto(BASE + "/ingestion.html")
    expect(page.locator("#logs")).to_contain_text("flagged.jpg")
    flagged = page.locator("#logs td.naming-issue")
    expect(flagged).to_have_count(2)
    assert flagged.all_text_contents() == ["white", "SM-A556E"]
    assert "not an accepted capture_device" in flagged.nth(1).get_attribute("title")
    assert (
        flagged.first.evaluate("e => getComputedStyle(e).backgroundColor")
        == "rgb(253, 224, 71)"
    )
    note = page.evaluate(
        "namingIssueNote({naming: %s})?.textContent" % __import__("json").dumps(NAMING)
    )
    assert note.startswith("Not in naming file — capture_env_lighting: white"), note
    assert "device: SM-A556E" in note and "identity" not in note
    assert page.evaluate("namingIssueNote({metadata: {}})") is None
    browser.close()
