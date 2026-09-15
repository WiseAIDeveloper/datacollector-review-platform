# Deployment

Start with the [README setup](../README.md#run-with-docker). Run the commands
below from the repository root. For version selection and image rollback, see the
[release guide](releases.md).

## Runtime configuration

Store deployment settings and credentials in a private `.env` file with mode
`600`. Keep an existing deployment's credential, dataset paths, and port. Never
paste credentials into source, documentation, logs, or pull requests.

Compose reads `.env` and passes only `DELETE_TOKEN` into the container at runtime.
Git and the Docker build context exclude `.env` and its variants. `.env.example`
contains no credential. The image copies an explicit list of application files
and receives no secrets during the build.

When run directly, the server accepts these additional environment variables:

| Variable        | Default                   | Purpose                                    |
| --------------- | ------------------------- | ------------------------------------------ |
| `DATA_ROOT`     | `/data`                   | Dataset directory                          |
| `INGESTION_DB`  | `/state/ingestion.sqlite` | Persistent ingestion and action database   |
| `INGESTION_LOG` | `/logs/ingestion.jsonl`   | Ingestion log output                       |
| `HOST`          | `0.0.0.0`                 | Server bind address inside its environment |
| `PORT`          | `8080`                    | Server port inside its environment         |

The supplied Compose file uses these internal defaults. Host storage paths and
the published address/port are controlled by the variables in `.env.example`.

## Persistent storage

| Resource              | Name or location                                     |
| --------------------- | ---------------------------------------------------- |
| Compose project       | `capture_viewer`                                     |
| Container             | `idrecapture-viewer`                                 |
| Capture dataset       | `${DATASET_PATH}` mounted at `/data`                 |
| Ingestion state       | `capture_viewer_ingestion_state` mounted at `/state` |
| Logs and review state | `${LOGS_PATH}` mounted at `/logs`                    |

Preserve the existing paths and volume on every upgrade. **`docker compose down -v`
deletes the named ingestion-state volume.** Release tags preserve code and image
identity; maintain separate backups of data, history, and private configuration.

The container uses a read-only root filesystem, drops Linux capabilities, and
disallows privilege escalation. Its data, state, and log mounts remain writable.

## Ingestion behavior

The worker scans every five seconds, independently of browser visits. Each unique
batch/UUID/filename is recorded once after its CSV row and nonempty original image
exist. Initial detections are `existing`; subsequent detections are `ingested`.

Detection time is distinct from upload time. Deleted captures stay in history.
API responses overlay current metadata while preserving the original detection
records and their timestamps.

## Verify a deployment

### 1. Preserve the current image and take a snapshot

Ensure the current image has a recorded rollback tag before replacing it. For the
first release, this is `capture_viewer-viewer:v1.0.0`; see the
[preserved image identity](releases.md#first-working-version-v100).

Use the actual service URL in place of `http://configured-host:8769`:

```sh
python scripts/verify_deployment.py snapshot --container idrecapture-viewer --url http://configured-host:8769 --output artifacts/before.json
```

### 2. Build and audit the candidate

```sh
docker compose config --quiet
docker compose build
python scripts/audit_image.py capture_viewer-viewer
```

The audit checks image metadata, history, and every layer for the active runtime
credential and local secret files without printing credential values. Run the
appropriate [application checks](development.md#run-checks) for the candidate.

### 3. Start the verified image

Within the authorized deployment scope:

```sh
docker compose up -d --no-build --wait
docker compose ps
docker compose logs --tail 50
```

`/health` returns `{"ok":true}` and is checked by Docker.

### 4. Compare data and configuration

```sh
python scripts/verify_deployment.py snapshot --container idrecapture-viewer --url http://configured-host:8769 --output artifacts/after.json
python scripts/verify_deployment.py compare artifacts/before.json artifacts/after.json
```

Snapshots contain hashes and counts, not credentials or raw capture metadata.
Comparison checks API responses, image samples, the full ingestion/action database
contents, log files, storage mounts, ports, and container restrictions. Transient
scanner status is excluded; persisted records and their timestamps are compared.

Concurrent legitimate dataset changes can produce differences. Inspect them
before attributing them to a deployment. Record results and any expected behavior
changes in the release notes; do not claim parity when differences remain unexplained.
