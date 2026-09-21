"""Exercise automatic folder discovery and project-local navigation in the browser."""

import os
import re
import shutil

from playwright.sync_api import expect, sync_playwright

from tests.support import running_server
from tests.test_folder_projects import add_folder

with running_server(folder_mode=True) as client, sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(client.base)
    expect(page.locator("h1")).to_have_text("Projects")
    expect(page.locator("#list-status")).to_contain_text("No projects yet")
    add_folder(client, "001_MyKad_ColourPrintEnhancement2")
    expect(
        page.get_by_role("heading", name="001_MyKad_ColourPrintEnhancement2")
    ).to_be_visible(timeout=10000)
    page.get_by_role("link", name="Open project", exact=True).click()
    expect(page.locator("header")).to_contain_text(
        "Project: 001_MyKad_ColourPrintEnhancement2"
    )
    page.locator(".batch").first.wait_for()
    for route in (
        "/coverage.html",
        "/",
        "/quality.html",
        "/search.html",
        "/ingestion.html",
    ):
        page.goto(client.base + route + "?project=001_MyKad_ColourPrintEnhancement2")
        banner = page.get_by_role("region", name="Current project", exact=True)
        expect(banner).to_contain_text("001_MyKad_ColourPrintEnhancement2")
        expect(banner.get_by_role("link", name="Switch project")).to_be_visible()
        expect(page).to_have_title(re.compile("001_MyKad_ColourPrintEnhancement2"))
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("link", name="Switch project", exact=True).click()
    expect(page.locator("h1")).to_have_text("Projects")
    page.get_by_role("link", name="Open selected project", exact=True).click()
    page.get_by_role("link", name="Ingestion logs", exact=True).click()
    assert "project=001_MyKad_ColourPrintEnhancement2" in page.url
    expect(page.locator("header")).to_contain_text(
        "Project: 001_MyKad_ColourPrintEnhancement2"
    )
    page.get_by_role("link", name="Capture review", exact=True).click()
    page.locator("#cards img").first.wait_for()
    page.wait_for_function("document.querySelector('#cards img')?.naturalWidth > 0")
    page.get_by_role("link", name="Projects", exact=True).click()
    add_folder(client, "002_Another", other=True)
    page.get_by_role("button", name="Refresh projects").click()
    expect(page.get_by_role("heading", name="002_Another")).to_be_visible()
    assert not errors, errors
    browser.close()
print(
    "PASS home project chooser, automatic folder detection, refresh, and project-local ingestion navigation."
)
