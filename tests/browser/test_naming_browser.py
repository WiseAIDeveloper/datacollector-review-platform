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
    """Serve an unknown name and a named value absent from the matrix."""
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
            total=4,
            existing=0,
            ingested=4,
            events=[
                event,
                dict(
                    event,
                    id=2,
                    filename="unplanned.jpg",
                    fields=dict(
                        capture_env_lighting="office_dark",
                        subject="fixture",
                        capture_device="galaxy_z_fold_5",
                    ),
                    naming={},
                ),
                *[
                    dict(
                        event,
                        id=number,
                        filename=marker + ".jpg",
                        available=False,
                        fields=dict(
                            capture_env_lighting="office_white",
                            subject="fixture",
                            capture_device="galaxy_z_fold_5",
                            replay_device=marker,
                        ),
                        naming={
                            "replay_device": dict(OK, issue="legacy issue")
                        } if marker == "none" else {},
                    )
                    for number, marker in [(3, "na"), (4, "none")]
                ],
            ],
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
    page.route(
        "**/api/fields*",
        lambda route: route.fulfill(
            json=[
                dict(key="capture_env_lighting", accepted=["office_white", "office_dark"], required=True),
                dict(key="subject", accepted=["fixture"], required=True),
                dict(key="capture_device", accepted=["galaxy_z_fold_5"], required=True),
                dict(key="replay_device", accepted=["galaxy_z_fold_5"], required=False),
            ]
        ),
    )
    page.route(
        "**/api/matrix*",
        lambda route: route.fulfill(
            json=[dict(folder="batch", sdk="app", test_plan_name="plan", capture_env_lighting="office_white", capture_device="galaxy_z_fold_5")]
        ),
    )
    page.goto(BASE + "/ingestion.html")
    expect(page.locator("#logs")).to_contain_text("flagged.jpg")
    flagged = page.locator("#logs td.naming-issue")
    expect(flagged).to_have_count(2)
    assert flagged.all_text_contents() == ["white", "SM-A556E"]
    assert "not an accepted capture_device" in flagged.nth(1).get_attribute("title")
    expect(page.locator("#logs td.ingestion-rainbow")).to_have_count(2)
    expect(page.locator("#logs td.ingestion-matrix-mismatch")).to_have_count(1)
    assert "linear-gradient" in flagged.first.evaluate(
        "e => getComputedStyle(e).backgroundImage"
    )
    assert flagged.first.evaluate("e => getComputedStyle(e).animationName") == "ingestion-gradient"
    assert "not planned" in page.locator("#logs td.ingestion-matrix-mismatch").get_attribute("title")
    for marker in ("na", "none"):
        replay = page.locator("#logs tr").filter(has_text=marker + ".jpg").locator("td").nth(6)
        expect(replay).to_have_text("—")
        assert "ingestion-rainbow" not in (replay.get_attribute("class") or "")
    note = page.evaluate(
        "namingIssueNote({naming: %s})?.textContent" % __import__("json").dumps(NAMING)
    )
    assert note.startswith("Not in naming file — capture_env_lighting: white"), note
    assert "device: SM-A556E" in note and "identity" not in note
    assert page.evaluate("namingIssueNote({metadata: {}})") is None
    browser.close()
