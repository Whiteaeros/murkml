# Contributing to murkml

Thank you for your interest in contributing to murkml!

## Development Setup

1. Clone the repository
2. Create a virtual environment: `uv venv .venv`
3. Activate: `.venv/Scripts/activate` (Windows) or `source .venv/bin/activate` (Unix)
4. Install in development mode: `pip install -e ".[all,dev]"`
5. Run tests: `pytest tests/`
6. Run linter: `ruff check src/`

## Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Ensure tests pass and linter is clean
5. Submit a pull request with a clear description

## Code Style

- We use `ruff` for linting and formatting
- Line length: 99 characters
- Type hints are appreciated but not required
- Add tests for new functionality

## Reporting Issues

Use GitHub Issues. Please include:
- What you were trying to do
- What happened instead
- Steps to reproduce
- Your Python and murkml versions
