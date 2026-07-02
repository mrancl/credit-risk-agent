import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "https://demoanaf.ro/mcp")
    mcp_timeout_seconds: float = float(os.getenv("MCP_TIMEOUT_SECONDS", "6"))
    mcp_tool_name: str = os.getenv("MCP_TOOL_NAME", "company_profile")
    mcp_auth_token: str = os.getenv("MCP_AUTH_TOKEN", "")
    score_threshold_approve: int = int(os.getenv("SCORE_THRESHOLD_APPROVE", "70"))
    score_threshold_review: int = int(os.getenv("SCORE_THRESHOLD_REVIEW", "40"))


settings = Settings()
