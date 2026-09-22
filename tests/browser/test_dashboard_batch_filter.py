"""Exercise single-batch dashboard filtering with disposable API fixtures."""

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from tests.support import asset_path

source = Path(os.environ["REVIEW_SOURCE"])
batch_names = ["alpha", "beta", "empty"]
matrix = [
    dict(
        folder=name,
        lighting="dark",
        sdk="web",
        device="iphone-13",
        expected_count_per_identity="2",
    )
    for name in batch_names
]
rows = [
    dict(
        key=f"{name}/{subject}/{index}.jpg",
        folder=name,
        sdk="web",
        device="iphone-13",
        line=index + 2,
        metadata=dict(
            uuid=f"{subject}-{index}",
            filename=f"{index}.jpg",
            subject=subject,
            lighting="dark",
            test_plan_name="colour_print_enhancement_2",
        ),
    )
    for name, count in [("alpha", 1), ("beta", 3)]
    for subject in ["person-a", "person-b"]
    for index in range(count)
]
data = {
    "captures": rows,
    "matrix": matrix,
    "batches": [
        dict(batch_name=name, batch_display_name=name.title(), sort_order=str(i))
        for i, name in enumerate(batch_names)
    ],
    "quality": {},
}


def route(request):
    """Serve application assets and synthetic API responses without live data."""
    path = urlparse(request.request.url).path
    if path.startswith("/api/"):
        request.fulfill(json=data.get(path[5:], {}))
        return
    asset = asset_path(source, path[1:])
    if asset.is_file():
        content_type = (
            "text/css"
            if path.endswith(".css")
            else "text/javascript" if path.endswith(".js") else "text/html"
        )
        request.fulfill(body=asset.read_text(), content_type=content_type)
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
    for width in [1440, 390]:
        data["matrix"] = matrix
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto("http://fixture/coverage.html")
        filters = page.get_by_role("group", name="Batches filter", exact=True)
        all_button = filters.get_by_role("button", name="All", exact=True)
        alpha = filters.get_by_role("button", name="alpha", exact=True)
        beta = filters.get_by_role("button", name="beta", exact=True)
        empty = filters.get_by_role("button", name="empty", exact=True)
        expect(all_button).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".batch")).to_have_count(3)
        expect(page.locator("#summary b")).to_have_text(["6", "4", "3", "1"])
        for card in page.locator("#summary .stat").all():
            assert card.evaluate("e => getComputedStyle(e).backgroundColor") == (
                "rgb(16, 19, 22)"
            )
            assert card.evaluate("e => getComputedStyle(e).borderTopColor") == (
                "rgb(39, 44, 49)"
            )
        expect(alpha).to_have_attribute("data-status", "in-progress")
        expect(beta).to_have_attribute("data-status", "excess")
        expect(empty).to_have_attribute("data-status", "not-started")
        for button, colour in [
            (alpha, "rgb(255, 141, 141)"),
            (beta, "rgb(244, 211, 94)"),
            (empty, "rgb(255, 141, 141)"),
        ]:
            assert button.evaluate("e => getComputedStyle(e).color") == colour
            assert button.evaluate("e => getComputedStyle(e).backgroundColor") == (
                "rgb(21, 26, 32)"
            )
            assert button.evaluate("e => getComputedStyle(e).borderTopColor") == (
                "rgb(54, 64, 74)"
            )

        # Complete Alpha while Beta has both missing and excess combinations.
        data["matrix"] = [
            (
                dict(item, expected_count_per_identity="1")
                if item["folder"] == "alpha"
                else item
            )
            for item in matrix
        ] + [dict(matrix[1], lighting="office")]
        page.locator("#refresh").click()
        expect(alpha).to_have_attribute("data-status", "completed")
        assert alpha.evaluate("e => getComputedStyle(e).color") == (
            "rgb(150, 230, 179)"
        )
        expect(beta).to_have_attribute("data-status", "excess")
        data["matrix"] = matrix
        page.locator("#refresh").click()
        expect(alpha).to_have_attribute("data-status", "in-progress")

        alpha.click()
        expect(alpha).to_have_attribute("aria-pressed", "true")
        expect(all_button).to_have_attribute("aria-pressed", "false")
        assert alpha.evaluate("e => getComputedStyle(e).color") == "rgb(255, 141, 141)"
        assert alpha.evaluate("e => getComputedStyle(e).boxShadow").count("inset") == 2
        assert all_button.evaluate("e => getComputedStyle(e).transform") == "none"
        expect(page.locator(".batch h2")).to_have_text(["Alpha"])
        expect(page.locator("#summary b")).to_have_text(["2", "1", "1", "0"])

        toggle = page.locator(".batch-filter-panel > summary")
        expect(toggle).to_have_text("Batches filter")
        toggle.click()
        expect(alpha).not_to_be_visible()
        expect(page.locator(".batch h2")).to_have_text(["Alpha"])
        page.locator("#refresh").click()
        expect(alpha).not_to_be_visible()
        toggle.focus()
        toggle.press("Enter")
        expect(alpha).to_be_visible()
        expect(alpha).to_have_attribute("aria-pressed", "true")

        beta.focus()
        beta.press("Enter")
        expect(beta).to_be_focused()
        expect(beta).to_have_attribute("aria-pressed", "true")
        expect(alpha).to_have_attribute("aria-pressed", "false")
        expect(page.locator(".batch h2")).to_have_text(["Beta"])
        expect(page.locator("#summary b")).to_have_text(["2", "3", "0", "1"])
        assert beta.evaluate("e => getComputedStyle(e).backgroundColor") == (
            "rgb(36, 42, 48)"
        )
        expect(beta).to_have_attribute("title", "Excess")

        page.locator('[data-view="excess"]').click()
        expect(page.locator(".group.over")).to_have_count(1)
        yellow = "rgb(244, 211, 94)"
        for selector in [
            "#summary .excess-count",
            "#view-title",
            ".lighting-block.has-excess > h3",
            ".group.over .badge .found-count",
            ".excess-review > summary",
        ]:
            assert (
                page.locator(selector).first.evaluate("e => getComputedStyle(e).color")
                == yellow
            ), selector
        assert (
            page.locator(".batch.excess").evaluate(
                "e => getComputedStyle(e).borderLeftColor"
            )
            == "rgb(82, 96, 107)"
        )
        page.locator('[data-view="batches"]').click()
        page.get_by_text("Show batch grouped by lighting", exact=True).click()
        expect(page.locator(".coverage-table .excess-case")).to_have_count(1)
        assert (
            page.locator(".coverage-table .excess-case td").first.evaluate(
                "e => getComputedStyle(e).backgroundColor"
            )
            == "rgb(16, 19, 22)"
        )

        for selector in [
            ".lighting-block.has-excess > h3",
            ".lighting-block.has-excess .coverage-table th",
        ]:
            assert (
                page.locator(selector).first.evaluate(
                    "e => getComputedStyle(e).backgroundColor"
                )
                == "rgb(21, 26, 32)"
            ), selector

        page.locator('[data-view="missing"]').click()
        expect(page.locator(".batch")).to_have_count(0)
        expect(page.get_by_text("No batches in this view.", exact=True)).to_be_visible()
        expect(filters.get_by_role("button")).to_have_count(4)
        empty.click()
        expect(page.locator(".batch h2")).to_have_text(["Empty"])
        expect(page.locator("#summary b")).to_have_text(["2", "0", "2", "0"])
        for selector in [
            '[data-view="missing"]',
            "#view-title",
            ".batch.missing > .batch-heading > h2",
            ".coverage-table .missing-case td:first-child",
        ]:
            assert (
                page.locator(selector).first.evaluate("e => getComputedStyle(e).color")
                == "rgb(255, 141, 141)"
            ), selector
        expect(page.locator(".coverage-table .missing-case")).to_have_count(1)
        assert (
            page.locator(".coverage-table .missing-case td").first.evaluate(
                "e => getComputedStyle(e).borderLeftColor"
            )
            == "rgb(53, 65, 75)"
        )
        all_button.click()
        assert all_button.evaluate("e => getComputedStyle(e).color") == (
            "rgb(196, 203, 210)"
        )
        assert (
            all_button.evaluate("e => getComputedStyle(e).boxShadow").count("inset")
            == 2
        )
        expect(page.locator(".batch h2")).to_have_text(["Alpha", "Empty"])
        expect(page.locator("#subject")).to_have_value("person-a")

        page.locator('[data-view="batches"]').click()
        beta.click()
        page.locator("#subject").select_option("person-b")
        expect(beta).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".batch h2")).to_have_text(["Beta"])
        page.locator("#refresh").click()
        expect(page.locator("#subject")).to_have_value("person-b")
        expect(beta).to_have_attribute("aria-pressed", "true")
        expect(page.locator('[data-view="batches"]')).to_have_text("All batches (1)")
        expect(page.locator('[data-view="excess"]')).to_have_text("Excess (1)")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        screenshots = source / "artifacts" / "batch-filter"
        screenshots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshots / f"dashboard-{width}.png"))

        all_button.focus()
        all_button.press("Space")
        expect(all_button).to_be_focused()
        expect(page.locator(".batch")).to_have_count(3)
        beta.click()
        data["matrix"] = [item for item in matrix if item["folder"] != "beta"]
        page.locator("#refresh").click()
        expect(beta).to_have_count(0)
        expect(all_button).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".batch h2")).to_have_text(["Alpha", "Empty"])
        data["matrix"] = []
        page.locator("#refresh").click()
        expect(filters.get_by_role("button")).to_have_count(1)
        expect(all_button).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#summary b")).to_have_text(["0", "0", "0", "0"])
        expect(page.locator("#summary .excess-count b")).to_have_text("0")
        assert (
            page.locator("#summary .excess-count").evaluate(
                "e => getComputedStyle(e).color"
            )
            == "rgb(244, 211, 94)"
        )
    # Refresh updates counts while preserving open and closed batch disclosures.
    data["matrix"] = matrix
    data["captures"] = rows
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto("http://fixture/coverage.html")
    alpha_card = page.locator(".batch").filter(has=page.locator("h2", has_text="Alpha"))
    lighting = alpha_card.locator("details[data-disclosure-key]").nth(1)
    definition = alpha_card.locator(".batch-definition")
    lighting.locator("summary").click()
    definition.locator("summary").click()
    data["captures"] = [*rows, dict(rows[0], key="new-capture")]
    page.locator("#refresh").click()
    expect(page.locator("#summary b")).to_have_text(["6", "5", "2", "1"])
    assert lighting.evaluate("node => node.open")
    assert definition.evaluate("node => node.open")
    definition.locator("summary").click()
    page.locator("#refresh").click()
    page.wait_for_timeout(100)
    assert not definition.evaluate("node => node.open")
    assert lighting.evaluate("node => node.open")
    page.locator("#subject").select_option("person-b")
    assert not lighting.evaluate("node => node.open")
    page.locator("#subject").select_option("person-a")
    assert lighting.evaluate("node => node.open")
    data["captures"] = rows
    # A second project's collector plan must drive identity choices and coverage.
    data["matrix"] = matrix
    data["captures"] = [
        dict(
            rows[0],
            metadata=dict(
                rows[0]["metadata"],
                subject="project-two-person",
                test_plan_name="002_mykad26_initialcollection",
            ),
        ),
        rows[-1],
    ]
    data["batches"] = [
        dict(batch, test_plan_name="002_mykad26_initialcollection")
        for batch in data["batches"]
    ]
    page.goto("http://fixture/coverage.html")
    expect(page.locator("#subject option")).to_have_text(["project-two-person"])
    expect(page.locator("#subject")).to_have_value("project-two-person")
    expect(page.locator("#summary b")).to_have_text(["6", "1", "5", "0"])
    expect(page.locator('#batch-filter button[data-batch="alpha"]')).to_have_attribute(
        "data-status", "in-progress"
    )
    # Both collector and review labels count in the same yellow requirement.
    data["matrix"] = [
        dict(matrix[0], lighting="office-yellow", expected_count_per_identity="2")
    ]
    sample = data["captures"][0]
    data["captures"] = [
        dict(
            sample,
            key=f"yellow-{i}",
            metadata=dict(sample["metadata"], lighting=lighting),
        )
        for i, lighting in enumerate(["yellow", "office-yellow", "dark"])
    ]
    page.goto("http://fixture/coverage.html")
    expect(page.locator("#summary b")).to_have_text(["2", "2", "0", "0"])
    expect(page.locator('#batch-filter button[data-batch="alpha"]')).to_have_attribute(
        "data-status", "completed"
    )
    data["matrix"] = [dict(data["matrix"][0], lighting="yellow")]
    page.locator("#refresh").click()
    expect(page.locator("#summary b")).to_have_text(["2", "2", "0", "0"])
    # White aliases share a requirement; yellow and dark remain separate.
    data["matrix"] = [
        dict(matrix[0], lighting="office-white", expected_count_per_identity="2")
    ]
    data["captures"] = [
        dict(
            sample,
            key=f"white-{i}",
            metadata=dict(sample["metadata"], lighting=lighting),
        )
        for i, lighting in enumerate(
            ["white", "office-white", "yellow", "dark", "office"]
        )
    ]
    page.goto("http://fixture/coverage.html")
    expect(page.locator("#summary b")).to_have_text(["2", "2", "0", "0"])
    data["matrix"] = [dict(data["matrix"][0], lighting="white")]
    page.locator("#refresh").click()
    expect(page.locator("#summary b")).to_have_text(["2", "2", "0", "0"])
    # Configured batches must remain selectable even before any captures arrive.
    data["captures"] = []
    data["matrix"] = matrix
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto("http://fixture/coverage.html")
    expect(page.locator("#batch-filter button")).to_have_text(["All", *batch_names])
    for filename, selector in [
        ("index.html", "#filters select"),
        ("quality.html", "#batch"),
    ]:
        page.goto("http://fixture/" + filename)
        select = (
            page.locator(selector).nth(1)
            if filename == "index.html"
            else page.locator(selector)
        )
        expect(select.locator("option")).to_have_text(["All", *sorted(batch_names)])
        select.select_option("empty")
        expect(select).to_have_value("empty")
        page.locator(
            "#refresh" if filename == "index.html" else "#refresh-quality"
        ).click()
        expect(select).to_have_value("empty")
    assert not errors, errors
    browser.close()

print(
    "PASS text-only status colours, neutral surfaces/borders, collapse/expand, "
    "batch selection, All reset, totals, status/identity filters, refresh, "
    "empty batches, removed selections, keyboard controls, and desktop/mobile layouts."
)
