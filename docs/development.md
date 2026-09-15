# Development

Follow [AGENTS.md](../AGENTS.md): use a feature branch, commit each focused change
with a concise message, document every function, and open a pull request for the
user to review and decide whether to merge. Add relevant changes to
[CHANGELOG.md](../CHANGELOG.md) and state their version impact.

## Architecture

| Module                                                  | Responsibility                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------------- |
| [app/settings.py](../app/settings.py)                   | Validate runtime configuration and keep credentials out of representations. |
| [app/captures/catalog.py](../app/captures/catalog.py)   | Read captures, collection annotations, and coverage definitions.            |
| [app/server.py](../app/server.py)                       | Handle HTTP requests and coordinate application startup and shutdown.       |
| [app/captures/deletion.py](../app/captures/deletion.py) | Validate and remove selected CSV rows and images.                           |
| [app/captures/editing.py](../app/captures/editing.py)   | Validate metadata edits and restore indexes after failed writes.            |
| [app/captures/quality.py](../app/captures/quality.py)   | Persist quality decisions and synchronize annotation statuses.              |
| [app/ingestion.py](../app/ingestion.py)                 | Scan captures, retain history, and export action logs.                      |

The frontend uses standalone HTML, JavaScript, and CSS. The refactor preserved
executable JavaScript behavior, checked against its parsed syntax tree. Importing
`app.server` starts no worker, opens no database, and requires no credential.

HTML lives in `web/pages/`; shared assets live in `web/static/js/` and
`web/static/css/`. `app.server.STATIC_FILES` maps the existing public URLs to these
locations, keeping internal package files outside the public routes.

### Entry points

After exporting the runtime credential and paths documented in
[deployment configuration](deployment.md#runtime-configuration), start the service
from the repository root:

```sh
python -m app
```

Inspect the deletion CLI without modifying any captures:

```sh
python -m app.captures.deletion --help
```

These replace `python server.py` and `python delete_capture.py` in direct source
invocations. The deletion arguments and application environment variables are
unchanged. Docker uses the module entry point automatically.

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

The [structure validation report](structure-validation.md) records checks for the
current folder reorganization and its Docker candidate.
