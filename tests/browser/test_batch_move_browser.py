"""Exercise batch editing through the browser against an isolated dummy server."""

import json
import os
import shutil
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from tests.support import IMAGE, running_server, write_csv

with running_server() as client, sync_playwright() as playwright:
    row = client.rows[0]
    key = "genuine/" + row["uuid"] + "/" + row["filename"]
    write_csv(
        next(client.root.glob("*_batches.csv")),
        [
            dict(
                batch_name=batch,
                test_plan_name=row["test_plan_name"],
                expected_capture_env_lighting=(
                    "office-white" if batch == "destination" else "dark;office-yellow"
                ),
            )
            for batch in ("genuine", "destination")
        ],
    )
    browser = playwright.chromium.launch(
        executable_path=os.environ.get("CHROME_PATH") or shutil.which("google-chrome"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(client.base + "/search.html")
    page.locator("#query").fill(row["uuid"])
    page.get_by_role("button", name="Search", exact=True).click()
    page.locator("#results button").first.click()
    expect(page.locator("#edit-batch")).to_have_value("genuine")
    page.locator("#edit-batch").select_option("destination")
    expect(
        page.locator('#edit-capture_env_lighting option[value="office-white"]')
    ).to_have_count(1)
    page.locator("#edit-capture_env_lighting").select_option("office-white")
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator("#save-metadata").click()
    assert client.request("/api/capture?key=" + key)[0] == 200

    def confirm(dialog):
        """Authorize writes using only the disposable fixture's runtime credential."""
        dialog.accept(client.token if dialog.type == "prompt" else "")

    page.on("dialog", confirm)
    page.locator("#save-metadata").click()
    expect(page.locator("#review-title")).to_contain_text("destination /")
    expect(page.locator("#edit-batch")).to_have_value("destination")
    expect(page.locator("#edit-capture_env_lighting")).to_have_value("office-white")
    page.wait_for_function('document.getElementById("review-image").naturalWidth > 0')
    new_key = "destination/" + row["uuid"] + "/" + row["filename"]
    assert client.request("/api/image?key=" + new_key)[1] == IMAGE
    assert client.request("/api/capture?key=" + key)[0] == 404
    assert not errors, errors
    browser.close()
print(
    "PASS batch dropdown, destination metadata choices, cancel without writes, real dummy move and reopened image."
)
