# Contributing to certfix

## Development Setup

```bash
# Clone repository
git clone <repository-url>
cd certfix

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode
pip install -e ".[dev]"
```

## Code Quality

### Linting and Formatting

```bash
# Check
ruff check src/ tests/ scripts/

# Fix automatically
ruff check --fix src/ tests/ scripts/

# Format
ruff format src/ tests/ scripts/
```

### Type Checking

```bash
mypy src/
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=certfix --cov-report=html

# Run specific test
pytest tests/unit/test_preprocessor.py
```

## Project Structure

Representative structure:

```text
src/certfix/
├── cli.py              # CLI commands
├── config.py           # Configuration loading
├── env.py              # .env loading
├── models.py           # Data models
├── output.py           # Text/JSON/SARIF output
├── prompt_profiles.py  # Prompt profile registry
├── prompts.py          # Prompt builders
├── core/
│   ├── detector.py              # Generic detector path
│   ├── simple_repair.py         # Fixed-code candidate generation
│   ├── fix_validator.py         # Validation gates
│   ├── validation.py            # Validation helpers
│   ├── validate_guided_retry.py # Retry support
│   ├── programmatic_checks.py   # Structural regression checks
│   ├── include_resolver.py      # Local include context
│   ├── splitter.py              # Function splitting helpers
│   └── preprocessor.py          # Comment handling
└── inference/
    ├── base.py       # Backend interface
    ├── api.py        # OpenAI-compatible API and local server backend
    ├── factory.py    # Backend construction
    └── parsing.py    # Model output parsing
```

## Commit Guidelines

- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Keep commits focused and atomic
- Write clear commit messages

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run `ruff check` and `mypy`
5. Submit PR with description

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
