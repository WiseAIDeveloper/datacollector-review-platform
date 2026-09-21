"""Verify actual CSV uploads and project navigation with disposable server state."""

import os
import shutil

from playwright.sync_api import expect, sync_playwright

from tests.support import MATRIX_NAME, running_server
from tests.test_projects import project_payload

with running_server() as client, sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(client.base + "/projects.html")
    expect(page.get_by_role("heading", name="Existing dataset")).to_be_visible()
    page.get_by_label("Project name").fill("Browser project")
    page.get_by_label("Test-plan CSV", exact=True).set_input_files(
        client.root / f"{MATRIX_NAME}.csv"
    )
    page.get_by_label("Batches CSV", exact=True).set_input_files(
        client.root / f"{MATRIX_NAME}_batches.csv"
    )
    page.get_by_label("Write PIN").fill("wrong")
    page.get_by_role("button", name="Create project").click()
    expect(page.locator("#create-status")).to_contain_text("Invalid deletion PIN")
    page.get_by_label("Write PIN").fill(client.token)
    page.get_by_role("button", name="Create project").click()
    expect(page.locator("#create-status")).to_contain_text("Project created")
    expect(page.get_by_label("Write PIN")).to_have_value("")
    page.get_by_role("link", name="Open Browser project").click()
    expect(page.locator("header")).to_contain_text("Project: Browser project")
    page.locator(".batch").first.wait_for()
    selected = page.url.split("project=")[1]
    page.get_by_role("link", name="Capture review", exact=True).click()
    assert "project=" + selected in page.url
    expect(page.locator("#cards article")).to_have_count(5)
    page.get_by_role("link", name="Image search", exact=True).click()
    assert "project=" + selected in page.url
    expect(page.locator("header")).to_contain_text("Project: Browser project")
    page.get_by_role("link", name="Quality review", exact=True).click()
    expect(page.locator("header")).to_contain_text("Project: Browser project")
    second = client.request(
        "/api/projects", project_payload(client, "Empty project", "other")
    )[1]
    other = browser.new_page()
    other.goto(client.base + "/coverage.html?project=" + second["id"])
    expect(other.locator("header")).to_contain_text("Project: Empty project")
    assert (
        page.evaluate(
            "async () => (await (await fetch('/api/captures')).json()).length"
        )
        == 5
    )
    assert (
        other.evaluate(
            "async () => (await (await fetch('/api/captures')).json()).length"
        )
        == 0
    )
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto(client.base + "/projects.html?project=" + selected)
        expect(
            page.get_by_role("heading", name="Browser project", exact=True)
        ).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=f"/tmp/projects-{width}.png", full_page=True)
    assert not errors, errors
    browser.close()
print(
    "PASS CSV uploads, failure recovery, navigation, independent tabs, and responsive projects page."
)
