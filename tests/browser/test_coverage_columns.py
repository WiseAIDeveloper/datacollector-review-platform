"""Check that matrix fields get separate coverage columns."""

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from tests.support import asset_path, fixture_fields, with_fields


source = Path(os.environ["REVIEW_SOURCE"])
fields = fixture_fields()
fields.insert(
    3,
    dict(
        key="replay_device",
        description="",
        role=None,
        column="replay_device",
        required=False,
        accepted=["google_pixel_9a"],
    ),
)
capture = with_fields(
    [
        dict(
            key="batch/person/one.jpg",
            folder="batch",
            sdk="web",
            device="iphone-13",
            line=2,
            metadata=dict(
                uuid="one",
                filename="one.jpg",
                subject="person",
                capture_env_lighting="dark",
                test_plan_name="plan",
            ),
        )
    ]
)[0]
capture["fields"]["replay_device"] = "google_pixel_9a"
data = dict(
    fields=fields,
    captures=[capture],
    matrix=[
        dict(
            folder="batch",
            sdk="web",
            capture_env_lighting="dark",
            capture_device="iphone-13",
            replay_device="google_pixel_9a",
            expected_count_per_identity="1",
        )
    ],
    batches=[dict(batch_name="batch", test_plan_name="plan")],
    quality={},
)


def route(request):
    """Serve local viewer assets and disposable API fixtures."""
    path = urlparse(request.request.url).path
    if path.startswith("/api/"):
        request.fulfill(json=data.get(path[5:], {}))
        return
    asset = asset_path(source, path[1:])
    if asset.is_file():
        kind = (
            "text/css"
            if path.endswith(".css")
            else "text/javascript" if path.endswith(".js") else "text/html"
        )
        request.fulfill(body=asset.read_text(), content_type=kind)
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
    page.goto("http://fixture/coverage.html")
    page.get_by_text("Show batch grouped by capture_env_lighting").click()
    expect(page.locator(".coverage-table th").first).to_be_visible()
    expect(page.locator(".coverage-table tr").first.locator("th")).to_have_text(
        [
            "capture_env_lighting", "SDK", "capture_device", "replay_device",
            "Expected", "Found", "Missing", "To add", "Reviewed",
        ]
    )
    expect(page.locator(".coverage-table tr").nth(1).locator("td")).to_have_text(
        ["dark", "WEB", "iphone-13", "google_pixel_9a", "1", "1", "0", "—", ""]
    )
    assert not errors, errors
    browser.close()

print("PASS coverage renders SDK and each planned device field in separate columns")
