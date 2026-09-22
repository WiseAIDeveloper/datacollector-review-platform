"""Isolated fixture browser tests; no live dataset mutations."""

import shutil
import os


from pathlib import Path
from tests.support import asset_path
from playwright.sync_api import sync_playwright, expect

src = Path(os.environ["REVIEW_SOURCE"])
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    saved = {}
    writes = []
    rows = [
        dict(
            key="batch/" + str(i) + "/image.jpg",
            folder="batch",
            sdk="web",
            device="iphone-13",
            metadata=dict(
                uuid=str(i), filename=str(i) + ".jpg", subject="person", lighting="dark"
            ),
        )
        for i in range(5)
    ]
    rows.append(
        dict(
            key="other/x/x.jpg",
            folder="other",
            sdk="app",
            device="phone",
            metadata=dict(uuid="x", filename="x.jpg", subject="other", lighting="dark"),
        )
    )
    page.route("**/*", lambda r: r.fulfill(body=""))
    page.route(
        "**/terminal.css",
        lambda r: r.fulfill(
            body=asset_path(src, "terminal.css").read_text(), content_type="text/css"
        ),
    )
    page.route(
        "**/quality.html*",
        lambda r: r.fulfill(
            body=asset_path(src, "quality.html").read_text(), content_type="text/html"
        ),
    )
    page.route("**/api/captures", lambda r: r.fulfill(json=rows))
    page.route("**/api/batches", lambda r: r.fulfill(json=[]))

    def quality(route):
        """Read or save quality decisions in the in-memory fixture store."""
        if route.request.method == "GET":
            route.fulfill(json=saved)
            return
        payload = route.request.post_data_json
        writes.append(payload)
        result = {**payload, "reviewed_at": "fixture"}
        saved[payload["key"]] = result
        route.fulfill(json=result)

    page.route("**/api/quality", quality)
    page.goto("http://fixture/quality.html?batch=batch&subject=person")
    expect(page.locator(".quality-card")).to_have_count(5)
    assert (
        page.locator("#page-number,#previous-page,#next-page,#dashboard-link").count()
        == 0
    )
    card = page.locator(".quality-card").first
    card.get_by_role("button", name="Quality error", exact=True).click()
    page.locator(".quality-card").nth(2).get_by_role(
        "button", name="Pass", exact=True
    ).click()
    assert page.locator("textarea,input[type=text]").count() == 0
    expect(page.locator("#save-reviews")).to_have_text("Save reviews (2)")
    page.once("dialog", lambda d: d.dismiss())
    page.locator("#save-reviews").click()
    assert not writes

    def accept(d):
        """Accept fixture confirmations and provide a disposable mock PIN."""
        d.accept("fixture") if d.type == "prompt" else d.accept()

    page.on("dialog", accept)
    page.locator("#save-reviews").click()
    expect(page.locator("#page-error")).to_have_text("2 review(s) saved.")
    assert len(writes) == 2
    assert (
        saved["batch/0/image.jpg"]["status"] == "error"
        and saved["batch/2/image.jpg"]["status"] == "pass"
    )
    page.reload()
    expect(page.locator(".quality-card")).to_have_count(5)
    assert page.locator("textarea").count() == 0
    page.locator("#quality-filter").select_option("error")
    expect(page.locator(".quality-card")).to_have_count(1)
    page.locator("#quality-filter").select_option("pass")
    expect(page.locator(".quality-card")).to_have_count(1)
    for w in [1440, 390]:
        page.set_viewport_size({"width": w, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors, errors
    b.close()
print(
    "PASS all five cards in scrolling grid, no pagination or Back to Dashboard, retained drafts, single top save confirmation, cancel without writes, pass/error notes persisted, filters, mobile layout."
)
