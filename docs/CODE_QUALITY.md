# Code Quality Guidelines

## Overview

Backend project enforces code quality through automated formatting, linting, and type checking. All code is automatically checked on commit via pre-commit hooks.

## Tools

- **black** - Code formatter (100 char line length)
- **isort** - Import organizer (black profile)
- **autoflake** - Removes unused imports and variables
- **flake8** - Style linter
- **mypy** - Static type checker

## Quick Start

### Install Development Tools

```bash
make install-dev
```

This installs all formatters/linters and sets up pre-commit hooks.

### Format Code (Auto-fix)

```bash
make format
```

Automatically:

- Removes unused imports and variables
- Sorts imports
- Formats code with black

### Run Linters

```bash
make lint
```

Runs flake8 and mypy checks (non-blocking).

### Run All Checks

```bash
make check
```

Runs all pre-commit hooks (same as what runs on commit).

### Format + Check

```bash
make fix
```

Formats code then runs all checks.

## Pre-commit Hooks

Hooks automatically run on `git commit`. They will:

1. **isort** - Sort imports
2. **autoflake** - Remove unused imports/variables
3. **black** - Format code
4. **flake8** - Lint code (relaxed for E402, F541)
5. **mypy** - Type check (backend only, scripts excluded)
6. **Basic checks** - Trailing whitespace, file endings, YAML/JSON/TOML validation

If any check fails, the commit is blocked. Run `make format` to auto-fix most issues.

## Configuration

### pyproject.toml

- **black**: 100 char lines, Python 3.11 target
- **isort**: black profile, first-party: ["app"]
- **autoflake**: Remove all unused imports, ignore **init**.py
- **mypy**: Strict type checking for backend/, relaxed for scripts/

### Flake8 Rules

- Max line length: 100
- Ignored: E203, W503, E501, E402, F541
- Max complexity: 20

### Type Checking

- **Backend** (`backend/`): Strict mypy checking

  - All functions must have type annotations
  - No untyped calls
  - Return types required

- **Scripts** (`scripts/`): Relaxed mypy checking
  - Type annotations optional
  - Untyped calls allowed
  - Focus on functionality over strict typing

## Common Issues

### Import errors after formatting

Run `make format` - autoflake + isort will fix.

### Type errors in scripts

Scripts have relaxed type checking. Focus on backend/ typing.

### Flake8 complexity warnings

Refactor complex functions (C901) or split into smaller functions.

### Pre-commit hook failures

1. Check error output
2. Run `make format` to auto-fix
3. Manually fix remaining issues
4. Re-commit

## CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Check code quality
  run: |
    pip install pre-commit
    pre-commit run --all-files
```

## Manual Commands

If you prefer not to use Makefile:

```bash
# Format
autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive backend/ scripts/
isort backend/ scripts/
black backend/ scripts/

# Lint
flake8 backend/ scripts/
mypy backend/

# Pre-commit
pre-commit run --all-files
```

## Best Practices

1. Run `make format` before committing
2. Keep functions under complexity 20
3. Add type hints to backend code
4. Remove unused imports immediately
5. Let black handle formatting - don't fight it
