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

## Verification

- Run checks appropriate to the change before committing, including relevant tests, linting, or builds where available.
- Resolve failures caused by the change and report any checks that could not be run.
