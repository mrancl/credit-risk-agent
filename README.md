# credit-risk-agent

Multi-agent credit-risk evaluator for Romanian companies, implemented with ADK 2.0.
Primary company data source: `https://demoanaf.ro/mcp`.

## Project Structure

```
my-agent/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and load tests
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Gemini CLI](https://github.com/google-gemini/gemini-cli) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/) ([add packages](https://docs.astral.sh/uv/concepts/dependencies/) with `uv add <package>`)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)


## Quick Start

Install `agents-cli` and its skills if not already installed:

```bash
uvx google-agents-cli setup
```

Install required packages:

```bash
agents-cli install
```

Test the agent with a local web server:

```bash
agents-cli playground
```

You can also use features from the [ADK](https://adk.dev/) CLI with `uv run adk`.

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `agents-cli install` | Install dependencies using uv                                                         |
| `agents-cli playground` | Launch local development environment                                                  |
| `agents-cli lint`    | Run code quality checks                                                               |
| `agents-cli eval`    | Evaluate agent behavior (generate, grade, analyze, and more — see `agents-cli eval --help`) |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests                                                        |

## 🛠️ Project Management

| Command | What It Does |
|---------|--------------|
| `agents-cli scaffold enhance` | Add CI/CD pipelines and Terraform infrastructure |
| `agents-cli infra cicd` | One-command setup of entire CI/CD pipeline + infrastructure |
| `agents-cli scaffold upgrade` | Auto-upgrade to latest version while preserving customizations |

---

## Development

Edit orchestration and scoring logic in:

- `app/agent.py` (root ADK agent)
- `app/agents/tools.py` (profile-based scoring tool)
- `app/integrations/` (payload normalization + schemas)
- `app/risk/policy.py` (deterministic score + recommendation policy)

Test locally with:

```bash
agents-cli playground
```

Example prompt:

```text
Evaluate credit risk for Romanian company CUI RO18547290. Return score, recommendation, confidence, and evidence.
```

## Configuration

Set these environment variables when needed:

- `MCP_SERVER_URL` (default: `https://demoanaf.ro/mcp`)
- `MCP_TIMEOUT_SECONDS` (default: `6`)
- `MCP_TOOL_NAME` (default: `company_profile`)
- `MCP_AUTH_TOKEN` (optional bearer token for remote MCP servers)
- `SCORE_THRESHOLD_APPROVE` (default: `70`)
- `SCORE_THRESHOLD_REVIEW` (default: `40`)

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

To add CI/CD and Terraform, run `agents-cli scaffold enhance`.
To set up your production infrastructure, run `agents-cli infra cicd`.

## Observability

Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging.
