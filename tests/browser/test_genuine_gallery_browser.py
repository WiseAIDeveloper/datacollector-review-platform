"""Exercise numbered image cards and existing review navigation in a browser."""

import os
import shutil

from playwright.sync_api import expect, sync_playwright

from tests.support import INDEXES, running_server, write_csv
from tests.test_folder_projects import add_folder


with running_server(genuine_gallery=True) as client, sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(client.base + "/genuine.html")
    expect(page.locator(".genuine-card")).to_have_count(3)
    expect(page.locator("#batch")).to_have_value("genuine")
    expect(page.locator('.genuine-card[data-number="1"]')).to_have_class(
        "genuine-card collected"
    )
    waiting = page.locator('.genuine-card[data-number="3"]')
    expect(waiting).to_contain_text("Waiting for samples")
    page.locator("#combination").select_option(label="iphone-13 · office-white · WEB")
    expect(page.locator('.genuine-card[data-number="1"]')).not_to_have_class(
        "genuine-card collected"
    )
    expect(page.locator('.genuine-card[data-number="2"]')).to_contain_text(
        "1 sample collected"
    )
    page.locator('.genuine-card[data-number="2"]').get_by_role(
        "link", name="View samples"
    ).click()
    expect(page.locator("#status")).to_contain_text("1 matching captures")
    assert page.evaluate("filters.lighting.value") == "office-white"
    page.go_back()
    page.locator("#batch").select_option("later")
    expect(page.locator(".genuine-card.collected")).to_have_count(0)
    page.locator("#batch").select_option("genuine")
    expect(page.locator('.genuine-card[data-number="1"]')).to_have_class(
        "genuine-card collected"
    )
    for position, count in enumerate((2, 4, 8)):
        page.locator("#density").evaluate(
            "(slider, value) => { slider.value = value; slider.dispatchEvent(new Event('input')); }",
            str(position),
        )
        expect(page.locator("#density-value")).to_have_text(str(count))
        assert page.locator("#genuine-cards").evaluate(
            "element => element.style.getPropertyValue('--gallery-columns')"
        ) == str(count)
    page.locator("#number-search").fill("3")
    expect(page.locator(".genuine-card:visible")).to_have_count(1)
    page.locator("#number-search").fill("")
    waiting.get_by_role("link", name="Coverage").click()
    expect(page.locator("#subject")).to_have_value("3")
    expect(
        page.locator('#batch-filter button[data-batch="genuine"]')
    ).to_have_attribute("aria-pressed", "true")
    page.go_back()
    waiting.get_by_role("link", name="Quality").click()
    expect(page.locator("#identity")).to_have_value("3")
    page.go_back()
    page.locator('.genuine-card[data-number="1"] a').first.click()
    expect(page.locator("#status")).to_contain_text("1 matching captures")
    page.go_back()
    expect(page.locator(".genuine-card")).to_have_count(3)
    # A new capture for number 3 should update its card without a page reload.
    rows = [dict(row) for row in client.rows]
    rows[2]["subject"] = "3"
    write_csv(client.root / "genuine" / INDEXES[0], rows)
    page.locator("#refresh").click()
    expect(waiting).to_have_class("genuine-card collected")
    expect(waiting).to_contain_text("1 sample collected")
    page.set_viewport_size({"width": 390, "height": 500})
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    assert page.evaluate(
        "document.querySelector('.genuine-card h2').getBoundingClientRect().top < innerHeight"
    )
    assert not errors, errors
    browser.close()

with running_server(
    folder_mode=True, genuine_gallery=True
) as client, sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    add_folder(client, "001_Genuine")
    page.goto(client.base)
    page.get_by_role("link", name="Open project", exact=True).click()
    expect(page).to_have_url(client.base + "/genuine.html?project=001_Genuine")
    expect(page.locator(".genuine-card")).to_have_count(3)
    expect(page.locator(".current-project-name")).to_have_text("001_Genuine")
    browser.close()
