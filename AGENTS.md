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

## Code Quality

- Keep code clean and concise, with descriptive names and small functions focused on one responsibility.
- Add a clear, concise docstring or comment to every function explaining its purpose; explain non-obvious constraints without narrating each line.
- Preserve existing behavior during refactoring. Add characterization tests for original functions before changing them, then run the same tests against the refactored implementation.
- Use disposable fixtures for tests, especially edits and deletions. Tests must not modify the live dataset.
- Before deploying a refactor, build and start its Docker image, verify behavior against the previous version, and preserve existing data and persistent volumes.

## Secrets and Sensitive Information

- Never expose passwords, PINs, tokens, credentials, or other sensitive information in source code, comments, tests, documentation, logs, commits, pull requests, or chat output.
- Store local secrets in `.env`, restrict its permissions, and exclude it from Git and Docker build contexts.
- Commit only `.env.example` with empty or clearly non-sensitive example values.
- Inject secrets at runtime. Do not hardcode them, pass them as Docker build arguments, or copy them into images or image layers.
- Use generated, disposable credentials in tests and check staged files and built images for accidental secret inclusion.
