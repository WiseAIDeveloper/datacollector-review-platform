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
    expect(page.locator('.genuine-card[data-number="1"]')).to_have_class(
        "genuine-card collected"
    )
    waiting = page.locator('.genuine-card[data-number="3"]')
    expect(waiting).to_contain_text("Waiting for samples")
    page.locator("#number-search").fill("3")
    expect(page.locator(".genuine-card:visible")).to_have_count(1)
    page.locator("#number-search").fill("")
    waiting.get_by_role("link", name="Coverage").click()
    expect(page.locator("#subject")).to_have_value("3")
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
