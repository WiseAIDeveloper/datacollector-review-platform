"""Verify project creation and quality review do not prompt for a write PIN."""

import shutil

from playwright.sync_api import expect, sync_playwright

from tests.support import running_server
from tests.test_folder_projects import add_folder

with running_server(
    folder_mode=True, write_pin_required=False
) as client, sync_playwright() as playwright:
    folder = add_folder(client, "001_NoPIN")
    browser = playwright.chromium.launch(
        executable_path=shutil.which("google-chrome"), args=["--no-sandbox"]
    )
    page = browser.new_page()
    dialogs = []

    def confirm(dialog):
        """Accept review confirmation while recording any unwanted PIN prompt."""
        dialogs.append(dialog.type)
        dialog.accept()

    page.on("dialog", confirm)
    page.goto(client.base)
    expect(page.locator("#pin")).to_be_hidden()
    page.get_by_label("Project name").fill("No PIN upload")
    page.get_by_label("Test-plan CSV", exact=True).set_input_files(folder / "plan.csv")
    page.get_by_label("Batches CSV", exact=True).set_input_files(
        folder / "plan_batches.csv"
    )
    page.get_by_role("button", name="Create project").click()
    expect(page.locator("#create-status")).to_contain_text("Project created")
    page.get_by_role("link", name="Open No PIN upload", exact=True).click()
    expect(page.get_by_role("region", name="Current project")).to_contain_text(
        "No PIN upload"
    )
    page.get_by_role("link", name="Quality review", exact=True).click()
    page.locator(".quality-card").first.get_by_role(
        "button", name="Pass", exact=True
    ).click()
    page.locator("#save-reviews").click()
    expect(page.locator("#page-error")).to_have_text("1 review(s) saved.")
    assert dialogs == ["confirm"], dialogs
    browser.close()
print("PASS project creation and quality save without a PIN; confirmation retained.")
