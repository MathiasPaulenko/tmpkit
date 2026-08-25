# Contributing to tmpkit

Thank you for your interest in contributing to tmpkit! This document describes the process and guidelines for contributing.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:

   ```bash
   git clone https://github.com/<your-username>/tmpkit.git
   cd tmpkit
   ```

3. **Install** in development mode:

   ```bash
   pip install -e ".[dev]"
   ```

4. **Create a branch** for your work:

   ```bash
   git checkout -b feat/my-feature
   ```

## Development Workflow

### Code Style

- **Formatter/Linter**: [ruff](https://docs.astral.sh/ruff/) is used for both linting and formatting.

  ```bash
  ruff check tmpkit/ tests/
  ruff format tmpkit/ tests/
  ```

- **Type checker**: [mypy](https://mypy-lang.org/) with `--strict`.

  ```bash
  mypy --strict tmpkit/
  ```

- **Python**: Target 3.11+ syntax. Use `from __future__ import annotations` in all modules.
- **Imports**: Sorted by ruff (isort-compatible). Stdlib first, then third-party, then local.

### Testing

- All new features must include tests.
- Tests live in `tests/unit/`, `tests/integration/`, and `tests/e2e/` and follow the `test_<module>.py` naming convention.
- Run the full suite:

  ```bash
  pytest tests/ -v
  ```

- Coverage must stay at or above **95%**:

  ```bash
  pytest --cov=tmpkit --cov-branch --cov-report=term-missing
  ```

### Pre-commit Hooks

This project uses pre-commit. Install hooks with:

```bash
pre-commit install
```

This runs ruff, mypy, and other checks on every commit.

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add spooled_temp_file support
fix: handle cross-filesystem dest move on Windows
docs: update README quick start
test: add edge case for keep_on_error
refactor: simplify _should_keep logic
```

### Pull Requests

1. **Branch naming**: `feat/<short-description>`, `fix/<short-description>`, `docs/<short-description>`.
2. **Keep PRs focused** — one feature or fix per PR.
3. **Update tests** — new code must be tested. Bug fixes should include regression tests.
4. **Update CHANGELOG.md** — add your change under `[Unreleased]`.
5. **Ensure CI passes** — all checks must be green before merge.

## Project Structure

```text
tmpkit/
├── tmpkit/              # Source code
│   ├── __init__.py      # Public API exports
│   ├── _sync.py         # Sync context managers
│   ├── _async.py        # Async context managers
│   ├── _atomic.py       # Atomic write
│   ├── _config.py       # DEBUG detection, keep logic
│   ├── _decorators.py   # @temp_dir() / @temp_file() decorators
│   ├── _registry.py     # Temp registry + cleanup hooks
│   ├── _types.py        # Type aliases, protocols
│   └── py.typed         # PEP 561 marker
├── tests/
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── e2e/             # End-to-end tests
├── pyproject.toml       # Build config, tool config
└── ref/                 # Internal design docs (not shipped)
```

## Reporting Issues

- **Bugs**: Use the bug report template. Include Python version, OS, and a minimal reproduction.
- **Features**: Use the feature request template. Explain the use case and expected API.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

Open a [discussion](https://github.com/MathiasPaulenko/tmpkit/discussions) or mention `@MathiasPaulenko` in your PR.
