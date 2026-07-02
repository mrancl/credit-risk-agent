# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

import google.auth
import os

from app.agents.tools import evaluate_company_credit_risk_from_profile
from app.config import settings
from app.integrations.demoanaf_auth import get_access_token

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


def _mcp_auth_headers(readonly_context=None) -> dict[str, str]:
    """Per-request headers with a fresh (auto-refreshed) OAuth access token."""
    return {"Authorization": f"Bearer {get_access_token()}"}


_mcp_headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
# header_provider is only consulted when a request context exists (i.e. during
# an agent run). Seed a static token too so tools/list works outside a run;
# missing credentials at import time are tolerated and surface at call time.
try:
    _mcp_headers["Authorization"] = f"Bearer {get_access_token()}"
except Exception:
    pass

mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=settings.mcp_server_url.rstrip("/"),
        headers=_mcp_headers,
        timeout=settings.mcp_timeout_seconds,
    ),
    tool_filter=settings.mcp_tool_filter,
    header_provider=_mcp_auth_headers,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a multi-agent credit risk evaluator for Romanian companies, backed by the "
        "DemoANAF MCP connector. To assess a company's risk:\n"
        "1. If you were given a company name instead of a CUI (fiscal code), call search_company "
        "to resolve the correct CUI first.\n"
        "2. Call get_company with the CUI to fetch the public company profile (legal name, fiscal "
        "status, VAT status, registration date, county, insolvency).\n"
        "3. Call get_company_financials with the CUI to fetch recent balance-sheet data (turnover, "
        "net profit, employee count).\n"
        "4. Merge the profile and the most recent year's financials into a single object and call "
        "evaluate_company_credit_risk_from_profile with the CUI and that merged object.\n"
        "Return the structured result and summarize score, recommendation, confidence, and key "
        "evidence. If a lookup fails or returns no data, say so explicitly instead of guessing."
    ),
    tools=[mcp_toolset, evaluate_company_credit_risk_from_profile],
)

app = App(
    root_agent=root_agent,
    name="app",
)
