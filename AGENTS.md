# Credit Risk Agent — Coding Agent Guide

> Project: `credit-risk-agent`  
> Purpose: Multi-agent credit-risk evaluator for Romanian companies, powered by ADK 2.0 and DemoANAF public data (`https://demoanaf.ro/mcp`).  
> Primary language: Python 3.11+  
> Package manager: `uv`  
> CLI: `google-agents-cli`

---

## Prerequisites

Install the CLI (one-time):

```bash
uv tool install google-agents-cli
```

You will also need:

- **uv** — Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **Google Cloud SDK** — for Vertex AI model access ([install](https://cloud.google.com/sdk/docs/install))
- **GCP credentials** — `gcloud auth application-default login` (or a service account with Vertex AI User role)

---

## Quick Start

```bash
# Install dependencies
agents-cli install

# Run the local interactive playground
agents-cli playground

# Run unit + integration tests
uv run pytest tests/unit tests/integration
```

---

## Architecture

The agent is implemented as a deterministic ADK 2.0 `Workflow` graph. The coordinator is not an LLM; it is a hard-coded pipeline where each edge is explicit.

```
START
  -> intake_agent            # scope gate + request parsing (LLM)
  -> route_intake
       out_of_scope -> decline_node          (terminal)
       in_scope     -> company_data_agent     # DemoANAF MCP: profile, financials, contracts (LLM)
                     -> parse_company_data
                          error -> error_report   (terminal)
                          ok    -> risk_score     # deterministic scoring policy, no LLM
                               -> prepare_sector_request
                               -> sector_analyst_agent   # CAEN peer benchmark (LLM)
                               -> parse_sector_analysis
                               -> prepare_report_request
                               -> report_writer_agent    # final report (LLM)
```

On the happy path there are **four LLM calls**: intake, company data collection, sector analysis, and report writing. The credit-risk score itself is computed deterministically in `app/risk/policy.py`.

### Agent Nodes

| Node | File | Responsibility |
|------|------|----------------|
| `intake_agent` | `app/agent.py` | Scope gate. Decides if the request is about Romanian company credit risk; extracts `company_query` and `language`. |
| `company_data_agent` | `app/agent.py` | Uses DemoANAF MCP tools to fetch company profile, financials, and public contracts. |
| `risk_score` | `app/agents/tools.py` | Normalizes MCP payload and runs deterministic scoring. |
| `sector_analyst_agent` | `app/agent.py` | Benchmarks the company against CAEN peers via `top_companies_by_slice_year`. |
| `report_writer_agent` | `app/agent.py` | Produces the final structured report in the user's language. |

### Guardrails

All guardrails live in `app/agents/guardrails.py`:

| Guardrail | Type | Attached to | Purpose |
|-----------|------|-------------|---------|
| `guard_user_input` | `before_model_callback` | `intake_agent` | Blocks prompt injection and profanity in user input. |
| `scrub_model_output` | `after_model_callback` | `report_writer_agent` | Masks profanity in final output. |
| `guard_tool_args` | `before_tool_callback` | `company_data_agent` | Validates/normalizes CUI arguments before MCP calls. |

The classifier uses a small LLM (`gemini-2.5-flash` by default, overridable via `GUARDRAIL_MODEL`) and **fails open**: a moderation outage will not crash the agent.

---

## Project Structure

```
credit-risk-agent/
├── app/
│   ├── agent.py                 # Root ADK Workflow graph and agent definitions
│   ├── config.py                # Settings dataclass (env-var driven)
│   ├── fast_api_app.py          # FastAPI server entrypoint
│   ├── agents/
│   │   ├── guardrails.py        # LLM-based safety guardrails + CUI validation
│   │   └── tools.py             # Risk scoring tool (profile -> JSON assessment)
│   ├── app_utils/
│   │   ├── telemetry.py         # OpenTelemetry / Cloud Logging setup
│   │   └── typing.py            # Shared type helpers
│   ├── integrations/
│   │   ├── demoanaf_auth.py     # OAuth token acquisition for DemoANAF MCP
│   │   ├── mcp_normalizer.py    # DemoANAF payload -> CanonicalCompanyProfile
│   │   └── schema.py            # Pydantic models for profiles and assessments
│   └── risk/
│       └── policy.py            # Deterministic credit-risk scorecard
├── scripts/
│   └── demoanaf_login.py        # Helper to authenticate with DemoANAF
├── tests/
│   ├── unit/                    # Unit tests for guardrails, policy, normalizer, pipeline
│   ├── integration/             # Live agent, guardrail, and server E2E tests
│   └── eval/                    # Eval datasets and eval_config.yaml
├── agents-cli-manifest.yaml     # agents-cli project metadata
├── pyproject.toml               # uv dependencies and tool config
└── AGENTS.md                    # This file
```

---

## Configuration

All runtime configuration is env-var driven and centralized in `app.config.settings`.

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_URL` | `https://demoanaf.ro/mcp` | DemoANAF MCP server endpoint |
| `MCP_TIMEOUT_SECONDS` | `15` | HTTP timeout for MCP calls |
| `MCP_TOOL_NAMES` | `search_company,get_company,get_company_financials,check_company_contracts,list_company_contracts,top_companies_by_slice_year` | Comma-separated allow-list of MCP tools |
| `MCP_AUTH_TOKEN` | `""` | Static OAuth token (fallback) |
| `SCORE_THRESHOLD_APPROVE` | `70` | Score >= this yields `approve` |
| `SCORE_THRESHOLD_REVIEW` | `40` | Score >= this and < approve yields `review`; below is `reject` |
| `GUARDRAIL_MODEL` | `gemini-2.5-flash` | Model used for safety classification |
| `GOOGLE_CLOUD_PROJECT` | auto-detected | GCP project for Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | `global` | Vertex AI location (do not change unless asked) |
| `GOOGLE_GENAI_USE_VERTEXAI` | `True` | Use Vertex AI instead of Gemini API |

The application sets `GOOGLE_CLOUD_LOCATION=global` and `GOOGLE_GENAI_USE_VERTEXAI=True` at import time. If you see model 404 errors, verify location/project credentials rather than changing the model name.

---

## Development Phases

### Phase 1: Understand Requirements
Before writing any code, understand the user's request in the context of the credit-risk domain: Romanian companies, CUI identifiers, DemoANAF data, and the deterministic scoring policy.

### Phase 2: Build and Implement
Implement agent logic in `app/`. Use `agents-cli playground` for interactive testing. Iterate based on user feedback.

Key files to edit for common changes:

- **Scoring logic** → `app/risk/policy.py`
- **MCP data normalization** → `app/integrations/mcp_normalizer.py`
- **Agent prompts / workflow** → `app/agent.py`
- **Guardrails** → `app/agents/guardrails.py`
- **Tool definitions** → `app/agents/tools.py`
- **Schemas** → `app/integrations/schema.py`

### Phase 3: The Evaluation Loop (Main Iteration Phase)
Start with 1-2 eval cases, run `agents-cli eval generate`, then `agents-cli eval grade`, iterate by making changes and rerunning both commands until satisfied. Expect 5-10+ iterations. Once you have a baseline, reach for `agents-cli eval compare` (regression diffs), `agents-cli eval analyze` (cluster failure modes), and `agents-cli eval optimize` (auto-tune prompts).

Eval config lives in `tests/eval/eval_config.yaml`. Custom metrics validate that the final JSON contains a numeric `score`, a valid `recommendation`, and non-empty `evidence`.

### Phase 4: Pre-Deployment Tests
Run `uv run pytest tests/unit tests/integration`. Fix issues until all tests pass.

### Phase 5: Deploy to Dev
**Requires explicit human approval.** Run `agents-cli deploy` only after user confirms.

### Phase 6: Production Deployment
Ask the user: Option A (simple single-project) or Option B (full CI/CD pipeline with `agents-cli infra cicd`).

---

## Development Commands

| Command | Purpose |
|---------|---------|
| `agents-cli install` | Install dependencies using uv |
| `agents-cli playground` | Interactive local testing |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests |
| `agents-cli eval dataset synthesize` | Synthesize multi-turn eval scenarios |
| `agents-cli eval generate` | Run agent on eval dataset, produce traces |
| `agents-cli eval grade` | Run agent evaluations on the traces |
| `agents-cli eval compare` | Compare two grade-results files (regression check) |
| `agents-cli eval analyze` | Cluster failure modes from grade results |
| `agents-cli eval metric list` | List built-in metrics available in the SDK |
| `agents-cli eval optimize` | Auto-tune agent prompts using eval data |
| `agents-cli lint` | Run code quality checks (ruff, codespell, ty) |
| `agents-cli infra single-project` | Set up project infrastructure (Terraform) |
| `agents-cli deploy` | Deploy to dev |
| `agents-cli scaffold enhance` | Add deployment target or CI/CD to project |
| `agents-cli scaffold upgrade` | Upgrade project to latest version |

---

## Testing

- **Unit tests** (`tests/unit/`): fast, no external credentials required. Cover guardrails, policy scoring, payload normalization, and pipeline wiring.
- **Integration tests** (`tests/integration/`): may require live DemoANAF credentials and GCP access. Use sparingly and never commit secrets.
- **Eval tests** (`tests/eval/`): behavior-driven evaluation using `agents-cli eval`.

When adding a feature, add a corresponding unit test first. Integration tests should only exercise end-to-end flows that cannot be validated at unit level.

---

## Operational Guidelines for Coding Agents

- **Code preservation**: Only modify code directly targeted by the user's request. Preserve all surrounding code, config values (e.g., `model`), comments, and formatting.
- **NEVER change the model** unless explicitly asked. The production model is `gemini-3.1-flash-lite` in `_make_model()`.
- **Model 404 errors**: Fix `GOOGLE_CLOUD_LOCATION` (e.g., `global` instead of `us-east1`), not the model name.
- **ADK tool imports**: Import the tool instance, not the module: `from google.adk.tools.load_web_page import load_web_page`
- **Run Python with `uv`**: `uv run python script.py`. Run `agents-cli install` first.
- **Stop on repeated errors**: If the same error appears 3+ times, fix the root cause instead of retrying.
- **Terraform conflicts** (Error 409): Use `terraform import` instead of retrying creation.
- **CUI handling**: CUIs can arrive as strings or integers. Always coerce to `str` before validation or MCP calls.
- **Deterministic scoring**: Keep `app/risk/policy.py` free of LLM calls. Every score adjustment must be traceable to a `RiskFactorScore` and `RiskEvidence` entry.
- **Guardrail fail-open**: Do not change the guardrails to raise on classifier errors; outages must not block legitimate users.
- **Secrets**: Never hard-code DemoANAF tokens or GCP credentials. Use environment variables or `demoanaf_login.py` for token acquisition.
