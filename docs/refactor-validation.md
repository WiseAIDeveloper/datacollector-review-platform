# Refactor validation

Validated on 2026-09-15 against original source revision `808746d` and the previously running Docker image.

## Results

| Check | Result |
| --- | --- |
| Original Python compatibility suite | 42 tests passed on the host and in the preserved original image. |
| Refactored Python suite | 47 tests passed on the host and in the exact deployed image. |
| Browser workflows | All 11 scripts passed against both original and refactored applications using disposable fixtures. |
| Visual comparison | All five pages matched at 1440px and 390px. Nine screenshots were identical; desktop coverage differed at 22 pixels by at most one RGB level, within the documented rasterization tolerance. |
| JavaScript behavior | Parsed executable syntax matched the original in all seven script-bearing files. |
| Formatting and function documentation | Python and frontend checks passed; a clean `npm ci` installation passed the documented frontend checks. |
| Live deployment | Container became healthy after `docker compose up -d --build --wait`. |
| API comparison | All 26 recorded response comparisons matched, including all 786 capture records and five samples each of capture details, images, annotations, and search. |
| Persistent state | All 802 ingestion events, 24 actions, initialization metadata, and ingestion/action/quality log hashes remained unchanged. |
| Runtime configuration | Dataset, state and log mounts, address, port, restart policy, read-only root, dropped capabilities, and privilege restrictions were preserved. |
| Secrets | The existing PIN was preserved in a mode-600, gitignored `.env`; tracked source and all eight image layers, image metadata, and history were checked for the active credential and local secret files. No matches were found. |
| Running code | Every deployed application file matched the current source hash, and ingestion scan timestamps continued advancing. |

Python tests cover the original deletion CLI, CSV byte preservation, metadata validation, optimistic conflicts, rollback, quality persistence across server restarts, ingestion recovery and history, HTTP validation, and the new configuration and lifecycle boundaries. Docker test runs used a read-only root, temporary files, no external network, and no production data mounts.

The existing header browser test assumed an alignment the original CSS no longer provides. It now verifies that Execute stays inside the sticky header and remains visible on desktop and mobile. The separate visual comparison verifies the existing layout against the original. Visual checks permit a difference of at most one RGB level in no more than 0.01% of pixels, accounting for Chrome's antialiasing rounding between page renders.

## Deployment details

- Previous image: `sha256:f2564817a9f487f49e978e8c54d4f520c3d20245077765fcd81eb8f7fa6cad52`.
- Deployed image: `sha256:73469c2e5905fd0fc7986e2e37774b0ec8c660a385c9289a881aad55d4da108e`.
- Previous image retained locally as `capture_viewer-viewer:before-refactor-808746d`.
- Container and volume names remain `idrecapture-viewer` and `capture_viewer_ingestion_state`.

Credential delivery intentionally changed from the old secret-file mount to a runtime environment variable populated from `.env`. Docker now has a health check, termination performs scanner cleanup, and access logs omit request paths and payloads. A rollback needs the previous image **and its original Compose secret-file configuration**.

Private deployment fingerprints and synthetic screenshots remain in the ignored `artifacts/` directory. The comparison excludes scan timestamps and other transient scanner status fields; persisted records and their timestamps are compared in full. Live validation used read requests only, and all mutation testing used disposable fixtures.
