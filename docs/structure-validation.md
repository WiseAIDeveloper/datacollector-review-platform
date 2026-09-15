# Project structure validation

Validated on 2026-09-15 for `refactor/project-structure`.

## Scope

Application modules now live in `app/`, capture operations in `app/captures/`,
pages in `web/pages/`, and shared assets in `web/static/`. Package imports, Docker
copy rules, static paths, test adapters, and developer tools follow the new layout.

The server starts with `python -m app`. The deletion CLI starts with
`python -m app.captures.deletion`; its arguments are unchanged. Public browser
URLs, API behavior, runtime settings, and persistent data formats are preserved.
Update external scripts that invoke the former root-level Python files.

## Results

| Check                                       | Result                                                                                                        |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Python regression suite before moving files | 47 tests passed.                                                                                              |
| Python regression suite after moving files  | 47 tests passed on the host and inside the candidate image.                                                   |
| Original implementation compatibility       | 42 tests passed against source revision `808746d` using the updated adapters.                                 |
| Browser workflows                           | All 11 scenarios passed on both the original and reorganized source using disposable fixtures.                |
| Frontend contents                           | All nine HTML, JavaScript, and CSS files are byte-for-byte identical to `v1.0.0`.                             |
| JavaScript behavior                         | All seven script-bearing files match the original executable syntax.                                          |
| Python behavior                             | All seven moved modules match `main` at `bf20a7d` after accounting for package imports and static-file paths. |
| Docker default startup                      | The real image entry point became healthy with five synthetic captures and isolated state/log storage.        |
| Docker contents                             | All 19 application and frontend files match the checkout.                                                     |
| Secret exclusion                            | All eight image layers, metadata, and history passed the runtime credential and local secret-file audit.      |
| Formatting and documentation                | Frontend formatting and Python formatting/docstring checks passed for all 35 Python files.                    |

Docker tests used no external network or production data mounts, a read-only root,
dropped capabilities, and temporary storage. The default-startup fixture needed
readable dataset permissions and container-owned temporary state/log mounts; an
initial attempt using private host-owned state directories could not open SQLite.
The corrected fixture passed without changing application code or container restrictions.

The frozen-header browser test had one remaining hardcoded deployment address.
It now reads from the same disposable fixture server as the rest of the browser suite.

## Images and release status

- Published baseline: [v1.0.0](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.0.0),
  source `1f2caffa7f6460282284cd17e565d3f31baf8889`.
- Preserved baseline image: `capture_viewer-viewer:v1.0.0`,
  `sha256:73469c2e5905fd0fc7986e2e37774b0ec8c660a385c9289a881aad55d4da108e`.
- Candidate image: `capture_viewer-viewer:project-structure`,
  `sha256:62fc4dc6901a19eb4bfbf89e9433e91cb2f8f3d292306cfb3a6101ffe6095c7e`.

The production container continues running v1.0.0. The folder reorganization and
new guides remain under **Unreleased** until reviewed and released; the published
tag has not moved. Current data is live and has changed since the historical
deployment comparison, so its original record counts are not a current data snapshot.
