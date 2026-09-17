# Changelog

User-visible changes are recorded here, newest first. Unreleased work is separate
from published versions. We follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A collapsible Batches filter with single-selection buttons and an All button on the dashboard.
  Cards, totals, and status counts follow the selected batch, which stays selected
  across identity changes, status views, and data refreshes.
- Batch buttons retain their dark style with status text: red for incomplete
  (including not started), green for completed, and yellow for excess.
  Excess takes priority. Selected batch buttons and All have a neutral inset
  pressed appearance, distinct from status colours.
- A `VERSION` file, release guide, and pull request checklist to keep version numbers,
  release notes, and verification records consistent.

### Changed

- Rename the dashboard's "Missing captures" summary to "Incomplete captures",
  retaining its red status text and capture count.
- Grouped Python application code under `app/`, capture operations under
  `app/captures/`, HTML under `web/pages/`, and shared assets under `web/static/`.
  Docker and developer tools now follow the package layout; public web routes,
  configuration variables, and stored data formats stay compatible.
- Changed direct source entry points to `python -m app` for the server and
  `python -m app.captures.deletion` for the deletion CLI. Existing CLI arguments
  are unchanged; update any scripts that invoke the former root-level files.
- Centralized configuration defaults and reused shared capture, deletion, and ingestion
  helpers (`65de613`). This cleanup is newer than the `v1.0.0` deployment.
- Reorganized the README into a quick start, feature overview, and links to detailed
  development, deployment, and release instructions.
- Required changelog updates and release version checks in `AGENTS.md`.

### Fixed

- Dashboard status colours now apply only to text. Summary cards, batch buttons,
  status tabs, quality-review links, cards, and tables use neutral dark surfaces
  and grey borders, including when excess captures are zero.
- Missing, not-started, and in-progress dashboard statuses use red text across
  batch buttons, status tabs, batch headings, coverage rows, and quality-review links.
- Made the frozen-header browser test read from its disposable fixture server
  instead of a hardcoded deployment address.

## [1.0.0] - 2026-09-15

First tagged release of the verified working application. The tag preserves source
commit `1f2caffa7f6460282284cd17e565d3f31baf8889`, which matches the running Docker
application files. Version tracking was introduced after this baseline, so this
historical tag does not contain `VERSION` or `CHANGELOG.md`.

### Added

- Established a release baseline for capture review, identity coverage, quality
  review, ingestion history, and image search.
- Added compatibility tests for the original and refactored implementations,
  isolated browser checks, visual comparisons, and Docker verification tools.
- Added a Docker health check and explicit application startup and shutdown.

### Changed

- Separated runtime settings, capture data access, and HTTP application coordination.
- Simplified and documented metadata editing, deletion, quality persistence, and
  ingestion code while preserving existing behavior.
- Formatted and documented the five pages and shared frontend scripts while
  preserving executable JavaScript and page appearance.

### Security

- Standardized runtime credential loading through a private, ignored `.env` file.
- Restricted the Docker build context to application files and excluded credentials
  from source, images, configuration representations, and request logs.

### Verification

- 42 compatibility tests passed against the original source and original image;
  47 tests passed against the refactored source and exact deployed image.
- All 11 browser scripts passed against both implementations. All five pages matched
  at desktop and mobile widths within the documented rendering tolerance.
- All 786 capture records and 26 API comparisons matched across deployment;
  802 ingestion events, 24 actions, and persistent log hashes were preserved.

See the [validation report](docs/refactor-validation.md) and
[release guide](docs/releases.md) for image identity and recovery details.

[Unreleased]: https://github.com/WiseAIDeveloper/datacollector-review-platform/compare/v1.0.0...main
[1.0.0]: https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.0.0
