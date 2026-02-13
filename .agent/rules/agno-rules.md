---
trigger: always_on
---

You are an expert in Python, the Agno framework, and AI agent system design.
Follow all rules below strictly. Do not improvise or relax constraints.

================================
GLOBAL PRINCIPLES
================================
- Prefer correctness, performance, and clarity
- Minimize runtime overhead
- Use production-safe defaults
- Avoid unnecessary abstractions

================================
HARD RULES (NON-NEGOTIABLE)
================================
1. NEVER create agents inside loops
   - Agents must be instantiated once and reused
   - Recreating agents causes severe performance degradation

2. ALWAYS use output_schema for structured output
   - Use Pydantic models
   - Do not return raw dicts or untyped JSON

3. DATABASE RULES
   - Production: PostgresDb ONLY
   - Development: SqliteDb allowed
   - Never recommend SQLite for production

4. START SIMPLE
   - Default to a single agent
   - Use Team or Workflow only when clearly required

5. NO EMOJIS
   - No emojis in examples, logs, comments, or print statements

6. NO UNNECESSARY F-STRINGS
   - Do not use f-strings when no variables are interpolated

================================
DEFAULT AGENT TEMPLATE
================================
Use this template unless explicitly instructed otherwise.

from agno.agent import Agent
from agno.models.openai import OpenAIChat

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    instructions="You are a helpful assistant",
    markdown=True,
)

================================
AGENT EXECUTION RULES
================================
- Use agent.run() for synchronous execution
- Use agent.arun() for async workflows
- In production, always wrap agent.run() in try-except

try:
    result = agent.run(query)
except Exception as e:
    raise RuntimeError("Agent execution failed") from e

================================
TOOLS USAGE
================================
- Add tools only when required
- Do not add tools preemptively

from agno.tools.websearch import WebSearchTools

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    tools=[WebSearchTools()],
    instructions="Search the web for accurate information",
)

================================
AGENT REUSE (CRITICAL)
================================
FORBIDDEN PATTERN:

for query in queries:
    agent = Agent(...)

REQUIRED PATTERN:

agent = Agent(...)
for query in queries:
    agent.run(query)

================================
PATTERN SELECTION
================================
SINGLE AGENT (DEFAULT, ~90%)
- One task or domain
- Tools + instructions are sufficient

TEAM PATTERN
- Multiple specialized agents required
- LLM decides task allocation
- Do NOT use if single agent is sufficient

from agno.team.team import Team

team = Team(
    members=[researcher, writer],
    model=OpenAIChat(id="gpt-4o"),
    instructions="Research and write articles",
)

WORKFLOW PATTERN
- Deterministic step ordering
- Conditional logic or branching required

from agno.workflow.workflow import Workflow
from agno.db.sqlite import SqliteDb

async def workflow_fn(session_state, topic: str):
    research = await researcher.arun(topic)
    article = await writer.arun(research.content)
    return article

workflow = Workflow(
    name="Workflow Name",
    steps=workflow_fn,
    db=SqliteDb(db_file="tmp/workflow.db"),
)

================================
KNOWLEDGE / RAG RULES
================================
- search_knowledge=True is MANDATORY
- Hybrid search preferred
- Cite sources in responses

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    knowledge=knowledge,
    search_knowledge=True,
    instructions="Use the knowledge base and cite sources",
)

Failure to enable search_knowledge invalidates RAG behavior.

================================
CHAT HISTORY
================================
- Enable ONLY when context continuity is required

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    db=SqliteDb(db_file="tmp/agents.db"),
    user_id="user-123",
    add_history_to_context=True,
    num_history_runs=3,
)

================================
STRUCTURED OUTPUT (MANDATORY)
================================
from pydantic import BaseModel

class Result(BaseModel):
    summary: str
    findings: list[str]

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    output_schema=Result,
)

result: Result = agent.run(query).content

Returning untyped or loosely structured data is forbidden.

================================
PRODUCTION DEPLOYMENT (AGENTOS)
================================
from agno.os import AgentOS
from agno.db.postgres import PostgresDb

agent_os = AgentOS(
    agents=[agent],
    db=PostgresDb(db_url=os.getenv("DATABASE_URL")),
)

app = agent_os.get_app()

Production settings:
- show_tool_calls=False
- debug_mode=False

================================
COMMON ERRORS (AVOID ALL)
================================
- Creating agents in loops
- Using Team when single agent is sufficient
- Forgetting search_knowledge=True
- Using SQLite in production
- Missing output_schema
- Adding unnecessary tools

================================
REFERENCE
================================
https://docs.agno.com
