# Contribution conventions

## Commit messages

Use short, imperative, lowercase Conventional Commit subjects with a single
scope when useful. The repository commonly uses these prefixes:

- `feat:` for user-visible capabilities
- `fix:` for bug fixes
- `opt:` for small behavior or configuration improvements
- `docs:` for documentation-only changes
- `chore:` for maintenance and generated-artifact updates
- `refactor:` for internal restructuring without intended behavior changes
- `test:` for test-only changes
- `ci:` for CI workflow changes

Keep the subject specific and concise, for example: `feat: add guardctl list
endpoints`. Keep unrelated changes in separate commits.

## Files that must not be committed

Never commit credentials, private keys, local runtime state, or generated
artifacts. These are ignored by this project:

- `.env`, `.local-secrets/`, and `.tasklattice-recovery/`
- `.venv/`, `node_modules/`, `controller/dist/`, and `controller/dist-server/`
- local caches, coverage output, databases, and Kubernetes state

Before staging, inspect `git status --short` and verify that no secret or local
state file is included. Generated contracts are committed when an API change
requires them; regenerate them with the project scripts rather than editing
them manually.

## Validation

Run the narrowest relevant tests first, then typecheck/build when touching
TypeScript. For API changes, regenerate and check the OpenAPI contract. Use
`git diff --check` before committing.
