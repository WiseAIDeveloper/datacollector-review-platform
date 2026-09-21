# Datacollector Review Platform

A web app for reviewing capture images, correcting metadata, and tracking collection
quality.

## What it does

- Browse, filter, and compare captures.
- Check identity coverage and find missing captures.
- Edit metadata, record quality decisions, or remove selected captures.
- Search by image ID and view ingestion history.

Saving changes requires a PIN. Removing a capture deletes its image files and
matching CSV rows.

## Projects

Open **Projects** in the sidebar to enter a project name and upload its test-plan
and batches CSVs (UTF-8, up to 400 KB each). Creating a project requires the existing
write PIN. Both files are validated together; invalid uploads create nothing.
Project names must be unique. The page lists the required CSV columns.

Choose **Open project** to view its dashboard. The project stays in the URL across
review and search pages, so tabs can select different projects. Captures match the
batches CSV's `batch_name` and `test_plan_name`; uploading plans does not upload
images. Projects may intentionally share matching captures and their reviews.
Ingestion logs remain dataset-wide. Unselected legacy URLs keep their existing behavior.

Definitions persist under `projects/` beside `INGESTION_DB` (normally `/state/projects`)
and must be included in state-volume backups. The existing CSV pair remains available
as **Existing dataset**. No dataset migration is required.

## Run with Docker

You need Docker Compose, a capture dataset, and a directory for logs.

For a new setup, create your local configuration:

```sh
cp .env.example .env
chmod 600 .env
```

Edit `.env` to set your private `DELETE_TOKEN`, `DATASET_PATH`, and `LOGS_PATH`.
For an existing deployment, keep its current configuration and storage paths.

Start the app:

```sh
docker compose up -d --build --wait
```

Open [http://127.0.0.1:8769](http://127.0.0.1:8769), or the address and port set in
`.env`. See the [deployment guide](docs/deployment.md) for upgrades and storage details.

## Project layout

```text
app/             Python application
  captures/      Capture catalog, editing, deletion, and quality
web/
  pages/         HTML pages
  static/js/     Shared JavaScript
  static/css/    Shared styles
tests/           Regression tests and browser checks
scripts/         Development and verification tools
docs/            Detailed guides
```

## Versions

[v1.1.0](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.1.0)
adds the collapsible dashboard batch filter, text-only status colours, and the
application folder layout shown above. The first verified working version remains
preserved as [v1.0.0](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.0.0).

See the [changelog](CHANGELOG.md) for changes by version and the
[release guide](docs/releases.md) for versioning and rollback.

## Development

See the [development guide](docs/development.md) for setup and tests, and
[AGENTS.md](AGENTS.md) for contribution rules. Submit changes through a pull
request for review.
