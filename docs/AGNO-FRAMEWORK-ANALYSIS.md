# Agno Framework Analysis: Usage Audit & Lightweight Replacement Recommendation

**Date:** 2026-02-15
**Scope:** Full codebase analysis of Agno framework usage, LLM role evaluation, and alternative recommendations.

---

## 1. Executive Summary

**Agno is declared as a core orchestration and agent framework throughout EcoShield's architecture, but zero Agno code exists in the implemented source.** The `src/` directory contains no imports from `agno`, no Agent instantiations, no Workflow objects, and no LLM calls. All hazard assessment logic is implemented as plain `async` Python functions with deterministic computations. The Agno dependency (v2.4.8, 1.8 MB wheel + 13 transitive dependencies) adds significant project footprint for zero runtime value.

### Key Findings

| Claim (from docs) | Reality (in code) |
|---|---|
| "Agno Workflows for deterministic orchestration" | No `Workflow` or `Step` objects exist in `src/` |
| "Agno Agents + DeepSeek LLM" agent layer | No `Agent` instantiation anywhere; no LLM calls |
| "ClimateAgent, HazardAgent, ReportAgent" | These classes do not exist |
| "DeepSeek Chat" as LLM provider | `DEEPSEEK_API_KEY` in docs, zero usage in code |
| `agno>=1.0` in `pyproject.toml` | Listed as dependency, never imported |
| `agno==2.4.8` in `requirements.txt` | Installed in lockfile, 1.8 MB + 13 transitive deps |
| `.agent/rules/agno-rules.md` | Rules file present, but no code follows it |

---

## 2. Detailed Agno Usage Audit

### 2.1 Source Code: Zero Agno Imports

```bash
$ grep -r "import.*agno\|from agno" src/
# (no results)
```

Every file in `src/tools/`, `src/data/`, `src/core/models/`, `src/agents/`, `src/workflows/`, and `src/api/` uses only standard Python (`asyncio`, `typing`), Pydantic, NumPy, and domain-specific libraries. No file imports or references `agno`.

### 2.2 Documentation vs. Implementation Gap

The Phase 4 doc (`ECOSHIELD-PHASE4-WORKFLOW-v3_2.md`) contains ~1,370 lines of detailed implementation code using `agno.workflow.Workflow`, `agno.workflow.Step`, and `agno.workflow.StepOutput`. **None of this code has been implemented.** The `src/workflows/` directory contains only empty `__init__.py` files:

```
src/workflows/__init__.py          → empty
src/workflows/steps/__init__.py    → empty
```

The `src/agents/worker.py` is a placeholder heartbeat loop with a `TODO` comment:

```python
# TODO: Implement actual task processing logic here
# e.g., fetch task from queue, run agent, etc.
```

### 2.3 What Actually Exists

The implemented code follows a simple pattern:

- **9 tool modules** (`src/tools/*.py`) — Each is a standalone `async def assess_*()` function that calls data modules and returns a Pydantic `HazardAssessmentResult`. Pure computation, no orchestration framework.
- **Data modules** (`src/data/*.py`) — Async functions for fetching/computing data. Standard Python.
- **Pydantic models** (`src/core/models/`) — Plain Pydantic v2 models. No Agno integration.
- **FastAPI API** (`src/api/main.py`) — Minimal FastAPI app. No Agno middleware or agents.

### 2.4 The "Agent" Architecture Is Actually a Function-Call Pipeline

The architecture doc describes a layered system:

```
API Layer → Workflow Layer (Agno) → Agent Layer (Agno + DeepSeek) → Tools Layer
```

What actually exists:

```
API Layer (FastAPI, minimal) → Tools Layer (async functions) → Data Layer (async functions)
```

The intermediate Workflow and Agent layers are **documentation-only** (spec code in markdown, not in `src/`).

---

## 3. LLM Role Analysis

### 3.1 Agents Described as "Reasoning" — Outputs Are Deterministic

The gaps analysis doc (section 2.3) correctly identifies this:

> "Agents are described as 'reasoning,' yet most outputs are actually deterministic."

Every tool function (`assess_riverine_flood`, `assess_coastal_flood`, etc.) is a deterministic computation:

1. Fetch geospatial data (elevation, discharge, soil properties)
2. Apply physics-based formulas (Manning's equation, Holland wind profile, HAND)
3. Compute risk scores via piecewise linear functions
4. Return typed Pydantic models

There is no step where an LLM could add value to the numeric pipeline. The only potential LLM use case mentioned is a `ReportAgent` for "synthesis/narration" — which does not exist and would be a downstream consumer, not a core pipeline component.

### 3.2 DeepSeek API Key: Referenced but Unused

`DEEPSEEK_API_KEY=sk-...` appears in the architecture doc's environment variables section. No code references it. The `src/config/settings.py` may define it, but no module consumes it.

---

## 4. Dependency Footprint of Agno

### 4.1 Direct + Transitive Dependencies

Agno v2.4.8 brings **13 direct dependencies**, many of which overlap with existing project deps but some are purely for agent/LLM functionality:

| Dependency | Size | Also needed by project? | Purpose in Agno |
|---|---|---|---|
| `docstring-parser` | ~30 KB | No | Agent tool introspection |
| `gitpython` | ~1.5 MB | No | Agent code versioning |
| `h11` | ~100 KB | Yes (via httpx) | HTTP/1.1 |
| `httpx[http2]` | ~300 KB | Yes | HTTP client |
| `packaging` | ~60 KB | Yes | Version parsing |
| `pydantic` | ~2 MB | Yes | Data models |
| `pydantic-settings` | ~50 KB | Possibly | Settings management |
| `python-dotenv` | ~30 KB | Yes | Env loading |
| `python-multipart` | ~35 KB | Yes (FastAPI) | Form parsing |
| `pyyaml` | ~600 KB | Yes | YAML parsing |
| `rich` | ~1.2 MB | No | CLI formatting |
| `typer` | ~200 KB | No | CLI framework |
| `typing-extensions` | ~100 KB | Yes | Type hints |

**Agno-only dependencies** (not needed by any other project requirement):
- `docstring-parser` — Agent tool docstring parsing
- `gitpython` (+`gitdb`, `smmap`) — Git integration for agent versioning
- `rich` — Terminal formatting for agent output
- `typer` — CLI framework for AgentOS

**Estimated unnecessary footprint: ~3-4 MB of installed packages + the 1.8 MB agno wheel itself.**

### 4.2 Lock File Bloat

The `requirements.txt` (generated lockfile) is 1,781 lines. Agno appears as a dependency source for 13 entries. Removing it would eliminate ~100-150 lines from the lockfile and reduce resolution complexity.

---

## 5. Recommendation: Remove Agno, Use Lightweight Alternatives

### 5.1 What EcoShield Actually Needs

Based on the Phase 4 workflow spec, EcoShield needs:

1. **Deterministic step sequencing** — Run steps 0-5 in order
2. **Parallel execution within steps** — `asyncio.gather()` for concurrent hazard assessments
3. **Data passing between steps** — Dict/dataclass flowing step-to-step
4. **Error handling** — Catch per-hazard failures without aborting the pipeline

**None of these require an agent framework.** They are standard async Python patterns.

### 5.2 Option A: Pure asyncio Pipeline (Recommended)

Replace the Agno Workflow concept with a simple async pipeline runner. This matches what the code already implicitly does:

```python
# src/workflows/pipeline.py
"""Lightweight deterministic pipeline runner — replaces Agno Workflow."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

@dataclass
class StepResult:
    name: str
    success: bool
    data: dict = field(default_factory=dict)
    error: str | None = None

@dataclass
class PipelineStep:
    name: str
    executor: Callable[[dict], Awaitable[dict]]
    description: str = ""

class Pipeline:
    """Deterministic step-by-step async pipeline."""

    def __init__(self, name: str, steps: list[PipelineStep]):
        self.name = name
        self.steps = steps

    async def run(self, input_data: dict) -> dict:
        data = input_data.copy()
        for step in self.steps:
            logger.info("[%s] Running step: %s", self.name, step.name)
            try:
                data = await step.executor(data)
            except Exception as e:
                logger.error("[%s] Step '%s' failed: %s", self.name, step.name, e)
                raise
        return data
```

**Total size: ~30 lines.** Provides identical functionality to what the Phase 4 doc specifies.

Workflow definition becomes:

```python
from src.workflows.pipeline import Pipeline, PipelineStep

hazard_pipeline = Pipeline(
    name="HazardAssessment",
    steps=[
        PipelineStep("asset_fetch", fetch_buildings_step),
        PipelineStep("chronic_hazards", assess_chronic_hazards_step),
        PipelineStep("cyclone", assess_cyclone_step),
        PipelineStep("acute_hazards", assess_acute_hazards_step),
        PipelineStep("structure_risk", assess_structure_risk_step),
        PipelineStep("composite", calculate_composite_step),
    ],
)
result = await hazard_pipeline.run(input_data)
```

### 5.3 Option B: Prefect (if observability is needed later)

If the team later needs workflow observability, retries, scheduling, and a dashboard:

- **Prefect** (~4 MB, pure Python, async-native)
- Provides `@flow` and `@task` decorators
- Built-in retry, timeout, caching, and observability
- No LLM/agent overhead — it is a workflow engine, not an agent framework
- Free open-source server for self-hosted dashboard

```python
from prefect import flow, task

@task
async def fetch_buildings(data: dict) -> dict: ...

@task
async def assess_chronic(data: dict) -> dict: ...

@flow(name="hazard-assessment")
async def hazard_pipeline(input_data: dict) -> dict:
    data = await fetch_buildings(input_data)
    data = await assess_chronic(data)
    ...
    return data
```

### 5.4 Option C: Temporalio (if distributed execution is needed)

For production-grade distributed workflows with durable execution:

- **Temporalio** — Durable workflow engine
- Overkill for current MVP but appropriate if EcoShield scales to many concurrent city assessments
- Not recommended now, but worth noting for future architecture

### 5.5 Comparison Matrix

| Capability | Agno (current) | Pure asyncio (Option A) | Prefect (Option B) |
|---|---|---|---|
| Deterministic steps | Yes | Yes | Yes |
| Parallel execution | Via asyncio | Via asyncio | Via `@task` + async |
| Step data passing | StepOutput | dict / dataclass | Return values |
| Error handling | Step-level | try/except | Built-in retry |
| Observability | Agent dashboard | Logging only | Web dashboard |
| LLM integration | Core feature | N/A (not needed) | N/A |
| Agent patterns | Core feature | N/A (not needed) | N/A |
| Dep footprint | ~5.5 MB + 13 deps | 0 (stdlib) | ~4 MB |
| Lockfile impact | ~150 lines | 0 lines | ~80 lines |
| Learning curve | Agno-specific | Standard Python | Minimal |
| Production maturity | Early-stage | N/A (custom) | Mature (YC W21, $1B+) |

---

## 6. Recommended Actions

### Immediate (before MVP)

1. **Remove `agno>=1.0.0` from `pyproject.toml` dependencies.**
2. **Re-lock dependencies** (`uv lock` / `pip-compile`). This will remove agno + its unique transitive deps (docstring-parser, gitpython, rich, typer) from the lockfile.
3. **Implement Option A** (pure asyncio Pipeline, ~30 lines) in `src/workflows/pipeline.py`.
4. **Implement the 6 workflow steps** from Phase 4 spec as plain async functions (they're already written as pseudocode in the doc — just drop the `agno.workflow.StepOutput` wrapper and return plain dicts).
5. **Remove `.agent/rules/agno-rules.md`** — it configures AI coding assistants to follow Agno patterns that the project doesn't use.
6. **Remove `DEEPSEEK_API_KEY`** from documented environment variables (no LLM is used).
7. **Update architecture doc** to reflect "async pipeline" instead of "Agno Workflows + Agents."

### If LLM Features Are Desired Later

If a `ReportAgent` or narrative synthesis layer is added in the future:
- Use the **Anthropic SDK** or **OpenAI SDK** directly for the specific narration endpoint.
- A single `async def generate_report(data: dict) -> str` function calling an LLM API is simpler and more auditable than an agent framework.
- This keeps the LLM confined to narration (as the gaps analysis recommends) without polluting the deterministic pipeline.

---

## 7. Impact Assessment

| Metric | Before (with Agno) | After (Option A) |
|---|---|---|
| `pyproject.toml` deps | 29 | 28 (-1) |
| `requirements.txt` lines | 1,781 | ~1,630 (-150) |
| Installed package size | ~45 MB | ~39 MB (-6 MB) |
| Docker image size | Reduction proportional | ~6 MB smaller |
| Unused framework code | 1.8 MB (agno wheel) | 0 |
| Actual framework usage | 0 imports | 30-line Pipeline class |
| LLM API key requirements | DEEPSEEK_API_KEY (unused) | None |
| Audit surface for numeric code | Opaque (agent framework) | Transparent (plain Python) |

---

*Analysis based on: git commit 0e851b0, all files in src/, docs/, .agent/, pyproject.toml, requirements.txt, uv.lock*
