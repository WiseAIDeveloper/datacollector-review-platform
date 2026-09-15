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
    reviews = {}
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    rows = [
        dict(
            key="genuine/" + str(i) + "/image.jpg",
            folder="genuine",
            sdk="web",
            device="iphone-13",
            line=2,
            metadata=dict(
                uuid=str(i),
                filename=str(i) + ".jpg",
                subject="person",
                lighting="dark",
                test_plan_name="colour_print_enhancement_2",
            ),
        )
        for i in range(3)
    ]
    page.route("**/*", lambda r: r.fulfill(body=""))
    page.route(
        "**/coverage.html*",
        lambda r: r.fulfill(
            body=asset_path(src, "coverage.html").read_text(), content_type="text/html"
        ),
    )
    page.route(
        "**/terminal.css",
        lambda r: r.fulfill(
            body=asset_path(src, "terminal.css").read_text(), content_type="text/css"
        ),
    )
    page.route("**/api/captures", lambda r: r.fulfill(json=rows))
    page.route("**/api/batches", lambda r: r.fulfill(json=[]))
    page.route(
        "**/api/matrix",
        lambda r: r.fulfill(
            json=[
                dict(
                    folder="genuine",
                    lighting="dark",
                    sdk="web",
                    device="iphone-13",
                    expected_count_per_identity="3",
                )
            ]
        ),
    )
    page.route("**/api/quality", lambda r: r.fulfill(json=reviews))
    page.goto("http://fixture/coverage.html#unreviewed")
    button = page.locator(".review-quality")
    expect(button).to_have_text("Unreviewed · 0/3")
    assert "unreviewed" in button.get_attribute("class")
    reviews[rows[0]["key"]] = {"status": "error"}
    page.locator("#refresh").click()
    expect(button).to_have_text("Reviewing · 1/3")
    assert "reviewing" in button.get_attribute("class")
    assert (
        button.evaluate("(e)=>getComputedStyle(e).backgroundColor") == "rgb(22, 54, 81)"
    )
    for r in rows:
        reviews[r["key"]] = {"status": "pass"}
    page.locator("#refresh").click()
    expect(page.locator(".batch")).to_have_count(0)
    page.locator('[data-view="batches"]').click()
    expect(button).to_have_text("Reviewed · 3/3")
    assert "reviewed" in button.get_attribute("class")
    page.get_by_text("Show batch grouped by lighting", exact=True).click()
    expect(page.locator(".reviewed-check")).to_be_checked()
    assert (
        button.evaluate("(e)=>getComputedStyle(e).backgroundColor") == "rgb(25, 60, 41)"
    )
    assert not errors, errors
    b.close()
print(
    "PASS dashboard grey/blue/green states, counts, unreviewed includes partial and excludes completed reviews."
)
