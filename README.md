# Datacollector Review Platform

Review capture images, check identity coverage, correct metadata, and track quality
decisions from one shared dataset.

**First stable release: [v1.0.0](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases/tag/v1.0.0)**
· Python + browser JavaScript · Docker Compose

[Quick start](#quick-start) · [Features](#features) · [Versions](#versions)
· [Development](docs/development.md) · [Deployment](docs/deployment.md)

## Features

| Page                   | What you can do                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| **Capture review**     | Filter and compare captures; draft Keep, Remove, Correct metadata, or Undecided decisions. |
| **Coverage dashboard** | Compare identities against the collection matrix and inspect missing or excess captures.   |
| **Quality review**     | Mark captures as pass, error, or unreviewed and save decisions to both annotation indexes. |
| **Ingestion logs**     | Inspect newly detected captures and recent edit or deletion actions.                       |
| **Image search**       | Find captures by UUID or filename and open their metadata editor.                          |

Reading requires no login. Writes require the runtime PIN and confirmation.
Review drafts stay in browser storage; saved decisions and ingestion history persist
on the server. Metadata edits reject stale snapshots to prevent overwriting newer changes.

> **Removing a capture deletes its matching CSV rows and image files.** Collection
> JSON and ingestion history remain. Use disposable data when testing writes.

## Quick start

**You need:** Docker with Compose, an existing capture dataset, and a writable log
directory. The application itself uses the Python standard library.

### 1. Choose your source

Use the current repository checkout for development. For the exact first stable
version, create a separate checkout:

```sh
git fetch origin tag v1.0.0
git worktree add --detach ../datacollector-review-platform-v1.0.0 v1.0.0
cd ../datacollector-review-platform-v1.0.0
```

`main` can contain changes newer than the latest release. The [changelog](CHANGELOG.md)
keeps those changes under **Unreleased**.

### 2. Configure privately

For a new checkout:

```sh
cp .env.example .env
chmod 600 .env
```

Edit `.env` locally. For an existing deployment, retain its `.env`, credential,
paths, and port instead of replacing them.

| Setting               | Purpose                                               | Default              |
| --------------------- | ----------------------------------------------------- | -------------------- |
| `DELETE_TOKEN`        | Private PIN required for writes                       | Required; no default |
| `DATASET_PATH`        | Absolute path to the capture dataset                  | Required             |
| `LOGS_PATH`           | Absolute path to persistent review and ingestion logs | Required             |
| `VIEWER_BIND_ADDRESS` | Host address exposed by Docker                        | `127.0.0.1`          |
| `VIEWER_PORT`         | Host port for the web interface                       | `8769`               |

The example paths must be replaced with real directories. `.env` is excluded from
Git and Docker build contexts; credentials enter the container only at runtime.

### 3. Start and check

```sh
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps
```

With the default address, open **[http://127.0.0.1:8769](http://127.0.0.1:8769)**.
Otherwise, use your configured host and port. `/health` returns `{"ok":true}` when
the server is responding, and Docker checks it automatically.

For upgrades, follow [deployment verification](docs/deployment.md#verify-a-deployment)
before replacing the running image.

## Versions

The working deployment is preserved as **v1.0.0**, with a Git tag and a matching
Docker image tag on the deployment host. The source tag identifies the exact
verified code; it does not include the dataset or private configuration.

- **What changed:** [Changelog](CHANGELOG.md)
- **Release notes and source:** [GitHub Releases](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases)
- **Version numbers, release checklist, and rollback:** [Release guide](docs/releases.md)
- **First-release test and data comparison results:** [Validation report](docs/refactor-validation.md)

We use [Semantic Versioning](https://semver.org/spec/v2.0.0.html): `1.0.1` for a
compatible fix, `1.1.0` for a compatible feature, and `2.0.0` for a breaking change.
Each change gets a changelog entry; each release gets a version bump. `VERSION`
tracks the latest release until the next release PR is prepared.

## Contributing

Start a feature branch, make focused commits with concise messages, document each
function, and run the relevant checks. Open a pull request with a summary,
verification results, and version impact. **The user reviews and decides whether
to merge.**

| Guide                              | Covers                                                               |
| ---------------------------------- | -------------------------------------------------------------------- |
| [Development](docs/development.md) | Architecture, test setup, and compatibility checks                   |
| [Deployment](docs/deployment.md)   | Runtime settings, persistent storage, and safe upgrades              |
| [Releases](docs/releases.md)       | Changelog entries, version bumps, tags, and rollback                 |
| [AGENTS.md](AGENTS.md)             | Required development, review, release, and secret-handling practices |
