# Changelog

User-visible changes are recorded here, newest first. Unreleased work is separate
from published versions. We follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Refresh dashboard data automatically every three seconds while the page is visible and no review is being edited. Manual and automatic refresh preserve selected filters, expanded details, review drafts, and scroll position; failed refreshes retain the last successful view.
- Keep the dashboard batch selector visible below the header while scrolling. Long batch lists scroll within the pane, and the pane can still be collapsed to make room for coverage results.

- Add an optional shared naming file (`NAMING_FILE`) with one block each for lighting, identity, and device: the column it is read from (App devices use `capture_device`, falling back to the auto-detected model), the accepted values, and device spellings keyed by column. Devices are shown by standard name; missing or unaccepted values are highlighted and edits must use accepted values. The project compose file mounts the shared `naming/` folder read-only. See `docs/naming.md`.

- Add an optional `replay_device` block to the naming file, for test plans that record the screen a card image is replayed on. Standard names and listed spellings are accepted, an empty value is allowed, and other values are highlighted. Existing naming files without the block keep working.

- Add `scripts/normalize_names.py` to convert old field values and spellings in capture indexes, annotations, and project plans to standard names (`--map field:old=new`), with a dry run and per-file backups.

- Add `--options` to the project audit to check that a collector plan only offers standard names for naming-file fields; plans may use any subset of fields and values.

- Add `scripts/rename_fields.py` to rename a stored field everywhere (capture index headers, annotation keys, plan headers, ingestion history and logs) and merge plan list columns, with a dry run and per-file backups.

### Changed

- Reconcile dashboard refresh and frozen batch selection with the deployed matrix naming, optional-field handling, ingestion highlights, and separate coverage columns so deployment preserves existing behavior.

- **Breaking:** the naming file now defines every capture field, and is required (`NAMING_FILE`, mounted from `NAMING_PATH` by both compose files). Each top-level key is a field whose name is its index column, matrix column, `expected_<field>` batch list, page label, and ingestion log key; one field has `role: identity` and one `role: device`. Pages, filters, edit forms, coverage, and audits follow the file instead of fixed lighting, identity, and device columns. Coverage matches each capture's batch, SDK, and every field the matrix has a column for, so unused fields such as a replay device do not affect it. Migrate with `scripts/rename_fields.py` and convert the naming file to the new format; see `docs/naming.md`.

- **Breaking:** the ingestion history stores field values by field name. An older database is converted on first start, keeping each old column's name; `scripts/rename_fields.py` renames them.

- Add a read-only project device audit to detect mismatched batch/matrix device lists and collector SDK/device pairs missing from project requirements.

### Fixed

- Show SDK, capture device, and replay device in separate coverage table columns when the matrix plans those fields.

- Include the naming module and shared field script in the Docker build context so the new viewer image starts correctly.

- Flag collector capture option fields absent from the naming file, and fail on broken option references, so stale field names cannot pass the project audit.

- Use the capture_device label when a recognized native sensor reports an Unknown model, without changing its App classification.

- Detect App/Web from recognized input sensor formats consistently across captures and ingestion. Native captures with a device label no longer become Web; unfamiliar sensors are explicitly unknown. Capture metadata is unchanged.

- Derive dashboard identities, coverage, review counts, and pending decisions from the selected project’s test plans instead of a hard-coded legacy plan.

- Show canonical project batch names in the dashboard filter and include configured batches with no captures in Capture and Quality filters.

### Changed

- Give review pages consistent title/action rows and compact project context. Group filters separately, collapse them on phones, and keep save/execute controls visible instead of hiding them in horizontally scrolling toolbars.

- Promote the project-based service to the main viewer name and port 8769; retain the original single-dataset deployment configuration for rollback.

- Compact the dashboard header into one desktop row with a smaller project indicator; remove the Plan files section.

- Remove the write PIN from the separate folder-project service, including project creation and review actions. Existing edit/delete confirmations remain.

### Added

- Show the current project in a prominent banner on review pages, with a Switch project link and the project name in the browser tab title.

- A separate Docker service discovers projects from folders, opens on project selection, and restores copied ingestion/action JSONL history into project-local databases. Each project keeps its own review logs and quality-review state. Existing shared-image URLs continue to load in review pages.

- Create named projects by uploading a test-plan CSV and batches CSV together. Select projects from the Projects page to scope dashboards, capture review, and search to their collection plans. Existing dataset access remains available. Project definitions persist in the state volume; creation uses the existing write PIN.

## [1.1.0] - 2026-09-17

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

[Unreleased]: https://github.com/WiseAIDeveloper/datacollector-review-platform/compare/v1.1.0...main
[1.1.0]: https://github.com/WiseAIDeveloper/datacollector-review-platform/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.0.0
