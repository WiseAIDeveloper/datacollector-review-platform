# Versions and releases

The first stable release is **v1.0.0**. [CHANGELOG.md](../CHANGELOG.md) describes
each version; [GitHub Releases](https://github.com/WiseAIDeveloper/datacollector-review-platform/releases)
provides its tag and release notes.

## What a version means

Use [Semantic Versioning](https://semver.org/spec/v2.0.0.html): `MAJOR.MINOR.PATCH`.
Compatibility covers the documented browser workflows, HTTP request and response
formats, persisted CSV and review data, and deployment configuration.

| Change                                                       | Example after 1.0.0 |
| ------------------------------------------------------------ | ------------------- |
| Compatible bug fix or maintenance release                    | `1.0.1`             |
| New compatible feature                                       | `1.1.0`             |
| Breaking workflow, API, data-format, or configuration change | `2.0.0`             |

Reset the lower numbers when increasing a higher one. Use a prerelease such as
`1.1.0-rc.1` when a candidate still needs validation; do not call it stable.

`VERSION` is the authoritative plain version number, without `v`. It records the
latest release until a release-preparation PR proposes the next one. Ordinary
feature branches add notes under **Unreleased** without bumping it for every commit.
A checkout with unreleased commits can therefore be newer than `VERSION`: use the
Git tag and commit to identify exact released source. The npm manifest is only for
private development tools and does not carry a second application version.

## Record changes as you work

- Update **Unreleased** in the same PR as each feature, fix, security change, or
  operational change. Describe the effect on users or operators in plain language.
- Use only relevant [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) groups:
  **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, and **Security**.
- Include migration, configuration, and data compatibility notes when applicable.
- State the intended version impact in the PR. Small documentation or test-only
  edits may say **no release needed** and explain why.
- Keep released entries intact. Correct factual errors transparently; do not move
  subsequent work into a published version or reuse its tag.

## Prepare the next release

1. Create a focused release branch from the current default branch. Select the next
   version based on all changes since the previous release.
2. In that PR, update `VERSION`, move the ready **Unreleased** notes into a dated
   `X.Y.Z` section using `YYYY-MM-DD`, and leave an **Unreleased** section for future work.
   Update the changelog comparison links and any version references in the README
   or deployment documentation. The initial retrospective release may include a
   separate **Verification** section; keep later verification in the release notes
   or linked reports.
3. Run the checks appropriate to the release. For application changes, follow
   [development checks](development.md) and [deployment verification](deployment.md).
   Record the exact source commit, image ID, test results, and any limitations.
4. Open a PR with a concise summary and review checklist. The user reviews and
   decides whether to merge. Do not merge or enable automatic merging yourself.
5. After the user merges and authorizes the release, verify the release commit is
   on the default branch, has the approved contents, and matches the tested source.
   Check that `VERSION`, the changelog heading, the tag, and release title agree.
   If the merged code differs from the tested candidate, rerun affected checks.
6. Create an **annotated** Git tag `vX.Y.Z` on that exact commit and push that tag
   explicitly. Publish a GitHub Release using its changelog entry and verification
   notes. Never force-push, delete, or move an existing published version tag.
7. Preserve the matching Docker image as `capture_viewer-viewer:vX.Y.Z`, recording
   its image ID. Deploy only within the user's authorized scope, preserve data and
   volumes, and verify health and data after deployment.

Version numbers change once per release, while changelog notes grow with each
change. A release request already authorized by the user does not require a second
approval; the user's separate decision to merge a PR still applies.

## First working version: v1.0.0

This is a retrospective tag of the verified deployment. Its source is already
included in merged PR #2. A later helper cleanup (`65de613`) is on `main` but is
outside this deployed baseline and belongs under **Unreleased**.

| Item                                    | Preserved identity                                                        |
| --------------------------------------- | ------------------------------------------------------------------------- |
| Git tag                                 | `v1.0.0`                                                                  |
| Source commit                           | `1f2caffa7f6460282284cd17e565d3f31baf8889`                                |
| Docker image tag on the deployment host | `capture_viewer-viewer:v1.0.0`                                            |
| Docker image ID                         | `sha256:73469c2e5905fd0fc7986e2e37774b0ec8c660a385c9289a881aad55d4da108e` |
| Evidence                                | [Refactor validation](refactor-validation.md)                             |

The first tag predates the version files and this guide. Those are introduced in a
separate documentation PR; the tag stays fixed on the actual working source.
Future release-preparation PRs include version metadata before tagging.

Inspect the preserved source without changing the active checkout:

```sh
git fetch origin tag v1.0.0
git show v1.0.0 --no-patch
git worktree add --detach ../datacollector-review-platform-v1.0.0 v1.0.0
docker image inspect capture_viewer-viewer:v1.0.0 --format '{{.Id}}'
```

The Docker tag is retained locally on the deployment host; it is not a registry
upload or an image archive. Git preserves source only. Keep data, persistent volumes,
and private runtime configuration separately backed up. Rebuilding a source tag
does not guarantee the same image bytes; retain the verified image for an exact
image rollback.

## Roll back to the preserved image

Use this only when a rollback is intended and authorized. From a checkout with the
compatible Compose configuration and private `.env`, create an ignored override:

```sh
mkdir -p artifacts
cat > artifacts/compose.v1.0.0.yaml <<'YAML'
services:
  viewer:
    image: capture_viewer-viewer:v1.0.0
YAML
docker compose -f compose.yaml -f artifacts/compose.v1.0.0.yaml config --quiet
docker compose -f compose.yaml -f artifacts/compose.v1.0.0.yaml up -d --no-build --pull never --wait
```

Take and compare deployment snapshots as described in [deployment verification](deployment.md#verify-a-deployment).
This reuses the dataset, log paths, and named state volume from the compatible
configuration. Application rollback does not restore previous dataset contents or
undo a future data migration; follow that release's migration and recovery notes.

The earlier **unversioned, pre-refactor** image is separately retained as
`capture_viewer-viewer:before-refactor-808746d`. It requires the original Compose
secret-file mount, whereas v1.0.0 uses the runtime environment from `.env`.
