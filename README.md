# Datacollector Review Platform

Review captures, compare identity coverage, correct metadata, and record quality decisions. The five pages share the same capture dataset and persistent ingestion history.

- **Capture review:** filter and compare captures, then mark Keep, Remove, Correct metadata, or Undecided. Drafts stay in browser storage.
- **Coverage dashboard:** compare each identity against the configured matrix and inspect missing or excess captures.
- **Quality review:** mark captures as pass, error, or unreviewed and save the decisions to both annotation indexes.
- **Ingestion logs:** inspect capture detections and recent edit/deletion actions. The worker scans every five seconds, independently of browser visits.
- **Image search:** find a capture by UUID or filename and open its metadata editor.

Reading the application requires no login. Writes require the runtime PIN and user confirmation. Executing a removal deletes matching CSV rows and image files; collection JSON and ingestion history remain. Metadata edits use an expected snapshot to reject stale changes.

## Runtime configuration

Store deployment settings and credentials in a local `.env` file:

```sh
cp .env.example .env
chmod 600 .env
```

Edit `.env` privately to set `DELETE_TOKEN`, `DATASET_PATH`, `LOGS_PATH`, and the desired bind address and port. For an existing deployment, preserve its current credential, paths, and port. Never paste credentials into source, documentation, logs, or pull requests.

Compose reads `.env` and passes only `DELETE_TOKEN` into the container at runtime. Both Git and the Docker build context exclude `.env` and its variants. `.env.example` contains no credential. The image copies an explicit list of application files and receives no secrets during the build.

The server also accepts `DATA_ROOT`, `INGESTION_DB`, `INGESTION_LOG`, `HOST`, and `PORT` when run directly. Docker uses `/data`, `/state/ingestion.sqlite`, `/logs/ingestion.jsonl`, and port 8080. Importing `server` starts no worker, opens no database, and requires no credential.

## Deploy

```sh
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail 50
```

Open the address configured by `VIEWER_BIND_ADDRESS` and `VIEWER_PORT`. `/health` returns `{"ok":true}` and is checked by Docker.

The Compose project remains `capture_viewer`, the container remains `idrecapture-viewer`, and ingestion history remains in `capture_viewer_ingestion_state`. Preserve that volume when deploying; `docker compose down -v` deletes it. The dataset and log directories use the paths in `.env`. The container retains a read-only root filesystem, drops Linux capabilities, and disallows privilege escalation.

Each unique batch/UUID/filename is recorded once after its CSV row and nonempty original image exist. Initial detections are `existing`; subsequent detections are `ingested`. Detection time is distinct from upload time. Deleted captures stay in history. API responses overlay current metadata while preserving the original detection records.

## Development

Follow [AGENTS.md](AGENTS.md): use a feature branch, commit each focused change with a concise message, document every function, and open a pull request for the user to review and decide whether to merge.

| Module | Responsibility |
| --- | --- |
| `settings.py` | Validate runtime configuration and keep credentials out of representations. |
| `capture_data.py` | Read captures, collection annotations, and coverage definitions. |
| `server.py` | Handle HTTP requests and coordinate application startup and shutdown. |
| `delete_capture.py` | Validate and remove selected CSV rows and images. |
| `edit_capture.py` | Validate metadata edits and restore indexes after failed writes. |
| `quality_reviews.py` | Persist quality decisions and synchronize annotation statuses. |
| `ingestion.py` | Scan captures, retain history, and export action logs. |

The frontend keeps its existing standalone HTML and JavaScript architecture. Formatting and function comments preserve the original executable JavaScript, checked against its parsed syntax tree.

### Install test tools

The application uses the Python standard library. Python 3.12 is used for development tooling; the Docker suite also verifies the app on its existing Python 3.10 runtime.

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
npm ci
```

Browser tests use `CHROME_PATH` if set, otherwise an installed Google Chrome or Playwright Chromium.

### Run checks

```sh
python -m unittest discover -s tests -t . -v
python -m tests.run_browser
python scripts/check_python.py
npm run format:check
npm run test:frontend
```

The Python suite exercises reads, searches, authentication, pagination, edits, deletions, conflicts, rollback, CSV byte preservation, ingestion, configuration, and worker lifecycle. The browser suite checks review workflows, filters, zoom, refresh, and desktop/mobile layouts.

All tests use synthetic temporary datasets. Browser write requests are mocked. Tests never modify the live dataset or use its credential.

### Verify against the original implementation

```sh
python scripts/test_original.py
python scripts/test_original.py --browser
```

These commands export revision `808746d` into temporary storage and run the same compatibility scenarios against it. `--revision` selects another baseline. The original server requires a small test adapter for its hardcoded paths and port; its request and storage logic are unchanged.

For visual comparisons, export the original revision to a temporary directory and run:

```sh
python -m tests.browser_parity /path/to/original-source
```

This compares all five pages at desktop and mobile widths using identical synthetic API responses. Only sparse one-level antialiasing differences are permitted. Screenshots are saved under ignored `artifacts/browser-parity/`.

### Verify a Docker deployment

Before replacing the running service, preserve its image with a rollback tag and take a snapshot:

```sh
python scripts/verify_deployment.py snapshot --container idrecapture-viewer --url http://configured-host:8769 --output artifacts/before.json
```

After building, check the image for credentials and secret files:

```sh
python scripts/audit_image.py capture_viewer-viewer
```

After deployment, take another snapshot and compare:

```sh
python scripts/verify_deployment.py snapshot --container idrecapture-viewer --url http://configured-host:8769 --output artifacts/after.json
python scripts/verify_deployment.py compare artifacts/before.json artifacts/after.json
```

Snapshots contain hashes and counts, not credentials or raw capture metadata. Comparison checks API responses, image samples, the full ingestion/action database contents, log files, storage mounts, ports, and container restrictions. Concurrent legitimate dataset changes can produce differences; inspect them before attributing them to a deployment.
