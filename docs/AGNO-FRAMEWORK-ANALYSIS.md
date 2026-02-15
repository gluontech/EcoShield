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

## 8. Revised Assessment: Keeping Agno for Future LLM-Driven Features

The original recommendation (sections 5-7) was based solely on the current codebase, where
Agno provides zero runtime value. However, the product roadmap includes features that
genuinely benefit from LLM reasoning. This section re-evaluates the trade-offs.

### 8.1 Future Features Where an LLM Adds Real Value

#### Asset Retrofitting Recommendations

This is the strongest case for LLM + agent integration. Retrofitting advice requires:

- **Multi-hazard reasoning** — A building with flood EAL of $12K/yr and wind damage ratio
  of 0.15 needs different interventions than one with subsidence at 40mm/yr. An LLM can
  weigh trade-offs across hazard types, building materials, and local construction costs.
- **Contextual knowledge** — Building codes (Vietnam QCVN, Philippine NSCPs), local
  material availability, cost databases. This is a classic RAG use case where Agno's
  `knowledge=` + `search_knowledge=True` pattern applies directly.
- **Natural language output** — Retrofit recommendations must be human-readable,
  actionable, and tailored to the building's risk profile. This is not deterministic.

Example Agno fit:
```
RetrofitAgent(
    model=DeepSeekChat(...),
    tools=[assess_structure_risk, lookup_building_codes, estimate_retrofit_cost],
    knowledge=local_building_code_kb,
    output_schema=RetrofitRecommendation,  # Pydantic structured output
)
```

#### Carbon / ESG / TCFD Reporting

Climate risk disclosure under TCFD, ISSB, and EU CSRD requires:

- **Narrative synthesis** — Translating quantitative risk outputs (EAL, damage ratios,
  hazard intensities) into regulatory-compliant disclosure language.
- **Scenario analysis narratives** — Explaining what SSP245 vs SSP585 means for a
  specific portfolio in plain language, with appropriate caveats.
- **Materiality assessment** — Interpreting which climate risks are "material" for a
  given portfolio composition. This involves judgment, not just thresholds.

Example Agno fit:
```
ReportAgent(
    model=DeepSeekChat(...),
    tools=[get_portfolio_summary, get_hazard_breakdown],
    output_schema=TCFDDisclosureSection,
)
```

#### Interactive Risk Q&A

A chat-based interface where users ask questions about their portfolio's risk:
- "Why is Building #4521 rated Critical?"
- "What would happen to our HCMC portfolio EAL if subsidence doubles?"
- "Compare our flood exposure in District 7 vs District 2."

This requires Agno's `chat history` + `memory` features, and the `Team` pattern could
coordinate a ClimateAgent (data retrieval) + AnalysisAgent (reasoning) + ReportAgent
(synthesis).

### 8.2 What Agno Provides That Matters for These Use Cases

| Agno Feature | Retrofitting | Carbon Reporting | Interactive Q&A |
|---|---|---|---|
| **Agent + Tool registration** | Tools = hazard assessors + cost estimators | Tools = portfolio queries + hazard summaries | Tools = all data access functions |
| **Structured output** (`output_schema`) | `RetrofitRecommendation` Pydantic model | `TCFDDisclosureSection` model | Typed responses |
| **Knowledge / RAG** | Building codes, material costs | TCFD/ISSB templates, regulatory guidance | Historical assessments |
| **Chat history / memory** | Not needed | Not needed | Core requirement |
| **Team** (multi-agent) | Possibly (cost agent + code agent) | Not needed | Climate + Analysis + Report agents |
| **Workflow** (deterministic) | Retrofit pipeline: assess → recommend → cost | Report pipeline: gather → synthesize → format | Not needed (dynamic Q&A) |
| **AgentOS** (deployment) | Production deployment wrapper | Same | Same |

### 8.3 The Case FOR Keeping Agno (Despite Current Non-Use)

**1. Avoiding a future re-integration tax.** If Agno is removed now and re-added in 6
months for retrofitting/reporting, the team will need to: re-learn the framework, re-add
the dependency, restructure the workflow layer to accommodate agents, and retrofit the
tool functions for Agno tool registration. The `agno-rules.md` file and architectural
decisions would need to be recreated.

**2. Tool registration is lightweight.** Agno's `tools=[assess_riverine_flood, ...]`
pattern means the existing async functions can be registered as agent tools without
modification. The current tool implementations (pure functions returning Pydantic models)
are already Agno-compatible — they just need to be wired up.

**3. Structured output is already aligned.** Every tool returns Pydantic models, which
is exactly what Agno's `output_schema` expects. There is no impedance mismatch.

**4. Dependency cost is modest.** The ~6 MB footprint increase from Agno is small relative
to the geospatial stack (numpy, scipy, xarray, rasterio, geopandas = ~200+ MB). Agno adds
< 3% to the total dependency footprint.

### 8.4 The Case AGAINST Keeping Agno (Even With Future Plans)

**1. YAGNI for 6+ months.** The MVP targets Q1-Q2 2026. Retrofitting and carbon reporting
are post-MVP features. Carrying an unused dependency for 6 months violates the principle
of only adding what you need now.

**2. Framework lock-in before validation.** Agno is relatively new (first stable release
2025). Committing to it now, before any agent code is written, means the team hasn't
validated that Agno's agent/team/workflow patterns actually fit EcoShield's specific
needs. Other agent frameworks (LangGraph, CrewAI, or direct SDK calls) might be better
suited — but that evaluation can't happen until agent features are actually built.

**3. The deterministic pipeline does not benefit.** Even with future LLM features, the
core hazard assessment pipeline (Steps 0-5) should remain deterministic and LLM-free, as
the gaps analysis correctly recommends. Agno Workflow is overkill for a sequential async
pipeline — it adds `StepOutput` wrappers, database persistence, and session management
that a 30-line Pipeline class handles equally well.

**4. LLM features can use Agno when they arrive.** Adding `agno` to `pyproject.toml` and
writing an agent takes 30 minutes when the feature is actually being built. The existing
tool functions will work as Agno tools without changes. There is no meaningful "re-
integration tax" — the functions are already Agno-compatible by design.

**5. Phantom architecture creates confusion.** The current state — where docs describe
an elaborate agent architecture that doesn't exist in code — actively misleads developers.
New team members will expect to find `ClimateAgent`, `HazardAgent`, and `ReportAgent` in
`src/agents/` and will instead find an empty heartbeat loop.

### 8.5 Revised Recommendation: Phased Approach

| Phase | Timeline | Framework | LLM |
|---|---|---|---|
| **MVP** (now) | Q1-Q2 2026 | Pure asyncio Pipeline | None |
| **v1.1** (reporting) | Q3-Q4 2026 | Keep Pipeline for hazards; add Agno for ReportAgent | DeepSeek or Claude for narration |
| **v2.0** (retrofitting) | 2027 | Pipeline + Agno agents for recommendations | LLM for reasoning + RAG |

**Concrete actions:**

1. **Now:** Remove `agno` from `pyproject.toml` and the lockfile. Implement the 30-line
   asyncio Pipeline for the hazard assessment workflow. Update docs to reflect reality.

2. **When building ReportAgent (v1.1):** Re-add `agno` with a scoped role. Create a
   `ReportAgent` that consumes `FullRiskProfile` and produces narrative reports. Register
   existing hazard tools on the agent for data retrieval. Keep the hazard pipeline
   deterministic and separate — the agent only touches narration.

3. **When building RetrofitAgent (v2.0):** Expand to Agno Team if multi-agent coordination
   is needed. Add RAG knowledge base for building codes. The `output_schema` pattern
   ensures structured, auditable recommendations.

**This approach gives you:**
- Clean MVP with no phantom dependencies
- Validated framework choice when LLM features actually ship
- Clear separation: deterministic numeric pipeline vs. LLM-powered reasoning
- No wasted effort — existing tools are already Agno-compatible by design

---

*Analysis based on: git commit 0e851b0, all files in src/, docs/, .agent/, pyproject.toml, requirements.txt, uv.lock*
