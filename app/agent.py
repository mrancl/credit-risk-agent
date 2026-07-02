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

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


_mcp_headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
if settings.mcp_auth_token:
    _mcp_headers["Authorization"] = f"Bearer {settings.mcp_auth_token}"

mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=settings.mcp_server_url.rstrip("/"),
        headers=_mcp_headers,
        timeout=settings.mcp_timeout_seconds,
    ),
    tool_filter=[settings.mcp_tool_name] if settings.mcp_tool_name else None,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a multi-agent credit risk evaluator for Romanian companies. "
        "When asked to assess company risk, first call the MCP company profile tool "
        "(typically named company_profile) with the requested company identifier. "
        "Then call evaluate_company_credit_risk_from_profile using the same company identifier and the MCP output. "
        "Return the structured result and summarize score, recommendation, confidence, and key evidence."
    ),
    tools=[mcp_toolset, evaluate_company_credit_risk_from_profile],
)

app = App(
    root_agent=root_agent,
    name="app",
)
