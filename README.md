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

[v1.0.0](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.0.0)
preserves the first verified working version. The folder layout above is part of
the newer, unreleased changes.

See the [changelog](CHANGELOG.md) for changes by version and the
[release guide](docs/releases.md) for versioning and rollback.

## Development

See the [development guide](docs/development.md) for setup and tests, and
[AGENTS.md](AGENTS.md) for contribution rules. Submit changes through a pull
request for review.
