---
trigger: always_on
---

## Style Guide
- Follow PEP 8 strictly.
- Use type hints for all function signatures.
- Use Google-style docstrings for all public methods.

## Architecture
- **Modularity**: Do not add logic directly to `main.py`. Create specialized modules in the `src/` directory and import them.
- **Dependencies**: Use `uv` for dependency management. If a new library is needed, run `uv` instead of using `pip`.

## Testing
- Every new feature must include a corresponding test file in the `tests/` folder using `pytest`.