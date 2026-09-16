# Development Practices

These practices apply to the `datacollector-review-platform` repository.

## Feature Branches

- Create a new Git branch before starting each feature.
- Use a descriptive branch name, such as `feat/user-authentication`.
- Keep each branch focused on one feature. Use separate branches for unrelated fixes or maintenance.
- Make changes on the working branch; do not commit directly to the default branch.

## Commits and GitHub

- Create a separate Git commit for each completed function or focused change.
- Include supporting tests and documentation in the same commit when they are needed for that change to work and be understood.
- Keep every commit coherent and reviewable; do not combine unrelated changes.
- Review the diff and stage only files relevant to the commit.
- Push completed commits to the corresponding feature branch on GitHub.

## Commit Messages

- Write clear, concise messages that describe what changed.
- Use the format `<type>: <short action in imperative form>`.
- Use types such as `feat`, `fix`, `refactor`, `test`, and `docs`.
- Examples: `feat: add password validation`, `fix: handle empty search results`, and `docs: define development practices`.
- Add a short body when the reason for a change needs explanation.

## Pull Requests and Review

- After pushing a completed feature or change, open a GitHub pull request against the repository's default branch.
- Use a clear, concise title and description explaining what changed, why, and how it was verified.
- Include a short checklist of changes and checks for the user to review.
- Share the pull request link with the user and leave it open for their review.
- The user will review the changes and decide whether to merge. Do not merge or enable automatic merging unless the user explicitly asks.

## Versioning and Release History

- Follow [docs/releases.md](docs/releases.md). Use Semantic Versioning (`MAJOR.MINOR.PATCH`): compatible fixes use a patch bump (`1.0.1`), compatible features use a minor bump (`1.1.0`), and breaking changes use a major bump (`2.0.0`). Reset lower components when bumping a higher one.
- Treat `VERSION` as the single application version source, without a `v` prefix. Git release tags use `vX.Y.Z`.
- Add a concise `CHANGELOG.md` entry under `Unreleased` in the same PR as each feature, fix, security change, or operational change. Use the relevant Added, Changed, Deprecated, Removed, Fixed, or Security sections; describe user impact and any migration steps.
- State the intended version impact in every PR. Documentation-only or test-only changes may state that no release is needed and explain any omitted changelog entry.
- Do not bump the version for every function or commit. When preparing a release, update `VERSION`, the dated changelog section, comparison links, and version references together in the release PR. Keep an `Unreleased` section for subsequent work.
- Before publishing, verify the version file, changelog, annotated tag, release title, tested source commit, and Docker image identity agree. Document any baseline exception explicitly; `v1.0.0` preserves the already verified source from before version metadata was introduced.
- The user decides whether to merge release PRs. Publish releases only within the user's authorized scope, after the source is reviewed and merged. An already authorized release does not need repeated permission.
- Tag the exact verified commit, push only the intended tag, and publish concise GitHub release notes from the changelog with validation results. Never move, overwrite, or delete published release tags, and never include unreleased work in a published version's notes.
- Preserve the verified Docker image under the matching version tag and record its image ID and rollback requirements. Preserve runtime secrets, datasets, and persistent volumes separately; a source or image tag is not a data backup.

## Verification

- Run checks appropriate to the change before committing, including relevant tests, linting, or builds where available.
- Resolve failures caused by the change and report any checks that could not be run.

## Feature Preview Testing

- Reserve host port **8770** (container port **8080**) for feature previews. Keep the existing service on its configured port (normally `8769`).
- When the user says they want to test a new feature, build the requested feature branch or PR and start a separate Docker container named `idrecapture-viewer-preview` on port `8770`; this request authorizes starting the preview without another confirmation.
- Use a separate preview image and isolated dataset copies or fixtures, ingestion state, logs, and runtime credentials. Do not share writable production data or state. The existing Compose file fixes the production container name, so changing only its project name or port is insufficient isolation.
- Check whether `8770` is occupied before starting. Replace only a confirmed previous preview; if another service owns the port, report the conflict instead of stopping it or silently choosing another port.
- Verify `/health` and the feature's relevant page or workflow, then share a browser-accessible URL (or an SSH tunnel command for a localhost binding), the tested branch/commit, and any limitations. Leave the preview running for the user's visual review.
- Wait for the user's verdict. Another agent may merge the PR after the user authorizes it; starting or approving a preview does not itself authorize merging or replacing the main service.

## Code Quality

- Keep code clean and concise, with descriptive names and small functions focused on one responsibility.
- Add a clear, concise docstring or comment to every function explaining its purpose; explain non-obvious constraints without narrating each line.
- Preserve existing behavior during refactoring. Add characterization tests for original functions before changing them, then run the same tests against the refactored implementation.
- Use disposable fixtures for tests, especially edits and deletions. Tests must not modify the live dataset.
- Before deploying a refactor, build and start its Docker image, verify behavior against the previous version, and preserve existing data and persistent volumes.

## Project Structure

- Keep application code in `app/`, with capture-specific catalog, editing, deletion, and quality logic in `app/captures/`. Group related responsibilities before adding new modules or packages.
- Keep HTML pages in `web/pages/`, shared JavaScript in `web/static/js/`, and stylesheets in `web/static/css/`. Preserve public URLs when moving files unless a behavior change is explicitly requested.
- Keep tests in `tests/`, browser scenarios in `tests/browser/`, developer and verification commands in `scripts/`, and detailed guides in `docs/`.
- Reserve the repository root for project metadata, entry-point documentation, dependency manifests, and Docker configuration. Do not scatter application modules or web assets at the root.
- Use package imports and `python -m app` to start the service. When moving code, update imports, Docker COPY rules and build exclusions, static routes, test source adapters, tooling, and documentation together.
- Keep tests usable against historical release layouts, and verify both the packaged application and the original behavior with disposable fixtures.

## Secrets and Sensitive Information

- Never expose passwords, PINs, tokens, credentials, or other sensitive information in source code, comments, tests, documentation, logs, commits, pull requests, or chat output.
- Store local secrets in `.env`, restrict its permissions, and exclude it from Git and Docker build contexts.
- Commit only `.env.example` with empty or clearly non-sensitive example values.
- Inject secrets at runtime. Do not hardcode them, pass them as Docker build arguments, or copy them into images or image layers.
- Use generated, disposable credentials in tests and check staged files and built images for accidental secret inclusion.
