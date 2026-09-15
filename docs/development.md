# Development

Follow [AGENTS.md](../AGENTS.md): use a feature branch, commit each focused change
with a concise message, document every function, and open a pull request for the
user to review and decide whether to merge. Add relevant changes to
[CHANGELOG.md](../CHANGELOG.md) and state their version impact.

## Architecture

| Module               | Responsibility                                                              |
| -------------------- | --------------------------------------------------------------------------- |
| `settings.py`        | Validate runtime configuration and keep credentials out of representations. |
| `capture_data.py`    | Read captures, collection annotations, and coverage definitions.            |
| `server.py`          | Handle HTTP requests and coordinate application startup and shutdown.       |
| `delete_capture.py`  | Validate and remove selected CSV rows and images.                           |
| `edit_capture.py`    | Validate metadata edits and restore indexes after failed writes.            |
| `quality_reviews.py` | Persist quality decisions and synchronize annotation statuses.              |
| `ingestion.py`       | Scan captures, retain history, and export action logs.                      |

The frontend uses standalone HTML, JavaScript, and CSS. The refactor preserved
executable JavaScript behavior, checked against its parsed syntax tree. Importing
`server` starts no worker, opens no database, and requires no credential.

## Install test tools

The application uses the Python standard library. Python 3.12 is used for
development tooling; the Docker suite also verifies the app on its existing
Python 3.10 runtime. Run these commands from the repository root, using a Python
virtual environment for the development dependencies:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
npm ci
```

Browser tests use `CHROME_PATH` if set, otherwise an installed Google Chrome or
Playwright Chromium.

## Run checks

```sh
python -m unittest discover -s tests -t . -v
python -m tests.run_browser
python scripts/check_python.py
npm run format:check
npm run test:frontend
```

The Python suite exercises reads, searches, authentication, pagination, edits,
deletions, conflicts, rollback, CSV byte preservation, ingestion, configuration, and
worker lifecycle. The browser suite checks review workflows, filters, zoom,
refresh, and desktop/mobile layouts.

All tests use synthetic temporary datasets. Browser write requests are mocked.
Tests never modify the live dataset or use its credential.

`test:frontend` checks executable JavaScript against the original refactor baseline.
An intentional frontend feature change needs behavior-focused tests and a reviewed
update to the applicable baseline; do not treat a syntax difference alone as a bug
or disable the check without explanation.

## Compare with the original implementation

```sh
python scripts/test_original.py
python scripts/test_original.py --browser
```

These commands export revision `808746d` into temporary storage and run the same
compatibility scenarios against it. `--revision` selects another baseline. The
original server requires a small test adapter for its hardcoded paths and port;
its request and storage logic are unchanged.

For visual comparisons, export the original revision to a temporary directory:

```sh
git archive 808746d --output /tmp/datacollector-original-source.tar
mkdir -p /tmp/datacollector-original-source
tar -xf /tmp/datacollector-original-source.tar -C /tmp/datacollector-original-source
python -m tests.browser_parity /tmp/datacollector-original-source
```

Use a fresh export directory for each baseline. The comparison covers all five
pages at desktop and mobile widths using identical synthetic API responses. Only
sparse one-level antialiasing differences are permitted. Screenshots are saved
under ignored `artifacts/browser-parity/`.

## Release checks

Use the [release checklist](releases.md#prepare-the-next-release) to choose a
version, update release notes, and record the verified source and image. For
application releases, also follow [deployment verification](deployment.md#verify-a-deployment).
