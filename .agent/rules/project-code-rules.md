---
trigger: always_on
---

# Project Rules & Standards

## 1. Project Structure

### 1.1 Respect Existing Layout
- **Never** restructure or rename existing folders without explicit instruction.
- Before creating any new file, inspect the current directory tree and place the file in the most semantically appropriate existing folder.
- When no suitable folder exists, create one that mirrors the project's established naming conventions.

### 1.2 Test Organization Rules
- Every source module maps to a corresponding file under `tests/unit/` that mirrors its relative path (e.g., `foo/bar.py` → `tests/unit/foo/test_bar.py`).
- Integration tests live under `tests/integration/` and mirror the service they exercise.
- Each test folder **must** contain an `__init__.py` so pytest discovery is consistent.
- Shared fixtures belong in the nearest-scope `conftest.py`; never duplicate fixture definitions.
- Test file names must start with `test_`; test functions must start with `test_`.

---

## 2. Asynchronous Programming

### 2.1 Async-First Policy
- All I/O-bound operations (network, filesystem, database, queues) **must** use `async`/`await`.
- Never introduce blocking calls inside a coroutine. Use `asyncio.to_thread()` or an executor to wrap unavoidably blocking third-party code.

```python
# ✅ Correct — offload blocking I/O
import asyncio

async def read_large_file(path: str) -> str:
    return await asyncio.to_thread(_blocking_read, path)

def _blocking_read(path: str) -> str:
    with open(path) as f:
        return f.read()
```

### 2.2 No Sync/Async Mixing
- A module is either **fully async** or **fully sync**; never mix paradigms within the same module.
- Never call `asyncio.run()` inside a coroutine or inside code that may already be running in an event loop.
- Use `asyncio.get_event_loop()` only at the top-level entry point; prefer `asyncio.run()` there instead.

```python
# ❌ Forbidden — blocks the event loop
async def fetch_data(url: str) -> bytes:
    return requests.get(url).content          # sync inside async

# ✅ Correct
import httpx

async def fetch_data(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.content
```

### 2.3 Concurrency Patterns
- Use `asyncio.gather()` for independent concurrent tasks; use `asyncio.TaskGroup` (Python ≥ 3.11) for structured concurrency.
- Set explicit timeouts with `asyncio.wait_for()` on every external call.
- Cancel tasks gracefully — always `await task.cancel()` and handle `asyncio.CancelledError`.

```python
# ✅ Structured concurrency with timeout
async def fetch_all(urls: list[str]) -> list[bytes]:
    async with asyncio.TaskGroup() as tg:
        tasks = [
            tg.create_task(asyncio.wait_for(fetch_data(url), timeout=10.0))
            for url in urls
        ]
    return [t.result() for t in tasks]
```

### 2.4 Async Context Managers & Generators
- Prefer `async with` for resource management (DB connections, HTTP sessions, file handles via `aiofiles`).
- Use `async for` when consuming async iterables; never `list()` wrap an async generator.

---

## 3. Thread Safety

### 3.1 Shared State
- Mutable shared state accessed by multiple coroutines or threads **must** be protected.
- Use `asyncio.Lock` for shared state inside an async context.
- Use `threading.Lock` (or `RLock`) only for state shared across OS threads.
- Never use a `threading.Lock` inside a coroutine — use `asyncio.Lock` to avoid blocking the event loop.

```python
import asyncio
from typing import ClassVar

class Counter:
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _value: ClassVar[int] = 0

    @classmethod
    async def increment(cls) -> int:
        async with cls._lock:
            cls._value += 1
            return cls._value
```

### 3.2 Queue-Based Communication
- Prefer `asyncio.Queue` over shared lists/dicts for producer–consumer patterns.
- For cross-thread communication use `queue.Queue`; never share `asyncio` primitives across OS threads.

### 3.3 Thread-Safe Singletons
- Implement singletons using `asyncio.Lock` during initialization; store the instance as a module-level variable after first creation.

```python
_instance: "MyService | None" = None
_init_lock = asyncio.Lock()

async def get_service() -> "MyService":
    global _instance
    if _instance is None:
        async with _init_lock:
            if _instance is None:           # double-checked locking
                _instance = await MyService.create()
    return _instance
```

### 3.4 Immutability First
- Prefer immutable data structures (`tuple`, `frozenset`, frozen `dataclass`, Pydantic models with `model_config = ConfigDict(frozen=True)`) to eliminate the need for locks altogether.

---

## 4. Python Best Practices

### 4.1 Type Annotations
- All public functions, methods, and class attributes **must** carry complete type annotations.
- Use `from __future__ import annotations` at the top of every module for forward references.
- Prefer built-in generics (`list[str]`, `dict[str, int]`) over `typing.List`, `typing.Dict` (Python ≥ 3.9).
- Use `typing.TypeAlias` for complex reused types; use `typing.TypeVar` for generic functions.

### 4.2 Data Modeling
- Use **Pydantic v2** models for all external data (API request/response, config, env vars).
- Use `@dataclass(slots=True, frozen=True)` for lightweight internal value objects.
- Never use plain `dict` as a function return type when a schema can be defined.

### 4.3 Error Handling
- Define a clear exception hierarchy rooted in a project-level base exception (e.g., `class AppError(Exception): ...`).
- Never catch bare `Exception` or `BaseException` unless re-raising or at the top-level error boundary.
- Always log the original exception with `logger.exception(...)` before wrapping and re-raising.

```python
class AppError(Exception): ...
class NotFoundError(AppError): ...
class ValidationError(AppError): ...

async def get_user(user_id: int) -> User:
    try:
        return await db.fetch_one(user_id)
    except DatabaseNotFoundError as exc:
        raise NotFoundError(f"User {user_id} not found") from exc
```

### 4.4 Logging
- Use the standard `logging` module; never use `print()` in library/service code.
- Obtain loggers via `logger = logging.getLogger(__name__)` at module level.
- Log at appropriate levels: `DEBUG` for trace/diagnostic, `INFO` for state changes, `WARNING` for recoverable issues, `ERROR`/`CRITICAL` for failures.
- Include structured context (user ID, request ID, correlation ID) using `LoggerAdapter` or `structlog`.

### 4.5 Configuration & Secrets
- Load all config from environment variables using **Pydantic Settings** (`BaseSettings`).
- Never hard-code secrets, hostnames, or port numbers anywhere in source code.
- Provide `.env.example` with all required keys (no real values).

### 4.6 Dependency Management
- Pin dependencies in `pyproject.toml` with minimum **and** maximum version bounds.
- Use a lockfile (`uv.lock` or `poetry.lock`) and commit it to source control.
- Separate `[project.dependencies]` (runtime) from `[project.optional-dependencies]` dev/test groups.

### 4.7 Code Style & Linting
- Format with **Ruff** (`ruff format`) — no manual formatting debates.
- Lint with **Ruff** (`ruff check`) and enforce at least: `E`, `F`, `I`, `UP`, `ASYNC` rule sets.
- Type-check with **mypy** (strict mode: `--strict`) or **pyright** (basic mode minimum).
- All checks **must pass** in CI before merge; never commit with suppressed lint errors unless accompanied by an explanatory comment.

### 4.8 Testing Standards
- Target ≥ 90 % branch coverage for all business logic and service modules; enforce with `pytest-cov --fail-under=90`.
- Use `pytest-asyncio` with `asyncio_mode = "auto"` for all async tests.
- Mock external I/O at the service boundary using `unittest.mock.AsyncMock` or `pytest-mock`.
- Tests must be **deterministic** — no `time.sleep()`, no random seeds without explicit fixture control.
- Each test must be independent; never rely on test execution order.

```python
# ✅ Async test example
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_fetch_user_returns_model(mock_db: AsyncMock) -> None:
    mock_db.fetch_one.return_value = {"id": 1, "name": "Alice"}
    user = await get_user(1)
    assert user.name == "Alice"
    mock_db.fetch_one.assert_awaited_once_with(1)
```

### 4.9 Documentation
- Every public module, class, and function must have a docstring (Google style).
- Docstrings must include `Args`, `Returns`, and `Raises` sections where applicable.
- Keep docstrings accurate — stale docs are treated as bugs.

### 4.10 Security
- Validate and sanitize **all** external inputs via Pydantic or explicit validators before use.
- Use `secrets` module for generating tokens/nonces; never use `random`.
- Avoid `eval()`, `exec()`, `pickle` on untrusted data.
- Review dependencies for known CVEs using `pip-audit` or `safety` in CI.

---

## 5. Quick-Reference Checklist

Before submitting any code, verify:

- [ ] File placed in the correct folder consistent with the existing project structure
- [ ] Corresponding test file created under `tests/` mirroring the source path
- [ ] All I/O is `async`; no blocking calls in coroutines
- [ ] No `threading.Lock` inside async code; `asyncio.Lock` used instead
- [ ] All public symbols have type annotations
- [ ] `ruff format`, `ruff check`, and `mypy --strict` pass with zero errors
- [ ] No secrets, hard-coded URLs, or magic numbers in source
- [ ] New logic covered by at least one unit test and one integration test
- [ ] Docstrings present on all public APIs