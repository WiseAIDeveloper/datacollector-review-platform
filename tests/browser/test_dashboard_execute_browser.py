"""Review execution against mocked APIs; never mutate the live dataset."""

import shutil
import os


from pathlib import Path
from tests.support import asset_path
from playwright.sync_api import sync_playwright, expect

src = Path(os.environ["REVIEW_SOURCE"])
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    writes = []
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    rows = [
        dict(
            key="genuine/" + i + "/" + i + ".jpg",
            folder="genuine",
            sdk="web",
            device="iphone-13",
            line=2,
            metadata=dict(
                uuid=i,
                filename=i + ".jpg",
                subject="fixture",
                lighting="dark",
                capture_device="iphone-13",
                test_plan_name="colour_print_enhancement_2",
            ),
        )
        for i in ["a", "b", "c", "d", "e"]
    ]
    page.route("**/*", lambda r: r.fulfill(body="", content_type="text/plain"))
    page.route("**/api/quality", lambda r: r.fulfill(json={}))
    page.route("**/api/captures", lambda r: r.fulfill(json=rows))
    page.route(
        "**/review",
        lambda r: r.fulfill(
            body=asset_path(src, "coverage.html").read_text(), content_type="text/html"
        ),
    )
    fail = [False]

    def write(route):
        """Record a mocked write and return the selected success or PIN failure."""
        writes.append((route.request.url, route.request.post_data_json))
        route.fulfill(
            status=403 if fail[0] else 200,
            json={"error": "bad PIN"} if fail[0] else {"updated": True, "deleted": 1},
        )

    page.route("**/api/edit-capture", write)
    page.route("**/api/apply-decisions", write)
    page.route(
        "**/api/matrix",
        lambda r: r.fulfill(
            json=[
                dict(
                    folder="genuine",
                    lighting="dark",
                    sdk="web",
                    device="iphone-13",
                    expected_count_per_identity="1",
                )
            ]
        ),
    )
    page.route(
        "**/api/batches",
        lambda r: r.fulfill(
            json=[
                dict(
                    batch_name="genuine",
                    test_plan_name="colour_print_enhancement_2",
                    expected_lighting="dark;office-white;office-yellow",
                    expected_identities="fixture;another",
                    expected_web_devices="iphone-13",
                )
            ]
        ),
    )
    page.goto("http://fixture/review#excess")
    page.locator(".excess-review summary").first.click()
    page.locator(".capture").first.wait_for()
    expect(page.locator(".capture")).to_have_count(5)
    page.locator(".capture").first.get_by_role(
        "button", name="Keep", exact=True
    ).click()
    expect(page.locator("#execute")).to_be_disabled()
    page.locator(".capture").first.get_by_role(
        "button", name="Correct metadata", exact=True
    ).click()
    page.locator(".capture").first.get_by_label(
        "Correct lighting", exact=True
    ).select_option("office-white")
    page.locator(".capture").nth(1).get_by_role(
        "button", name="Remove", exact=True
    ).click()
    page.once("dialog", lambda d: d.dismiss())
    page.locator("#execute").click()
    assert not writes

    def accept(d):
        """Accept fixture confirmations and provide a disposable mock PIN."""
        d.accept("fixture") if d.type == "prompt" else d.accept()

    page.on("dialog", accept)
    fail[0] = True
    page.locator("#execute").click()
    expect(page.locator("#execute")).to_have_text("Execute decisions (2)")
    assert len(writes) == 1
    fail[0] = False
    page.locator("#execute").click()
    expect(page.locator("#execute")).to_have_text("Execute decisions (0)")
    assert writes[1][1]["changes"] == {"lighting": "office-white"}
    assert writes[2][1]["remove"][0]["uuid"] == "b"
    assert page.locator("#export,#csv").count() == 0
    assert not errors, errors
    browser.close()
print(
    "PASS Keep unchanged; confirmation cancel; failed PIN preserves drafts; correction + removal execution; successful drafts cleared; exports removed."
)
