import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "https://demoanaf.ro/mcp")
    mcp_timeout_seconds: float = float(os.getenv("MCP_TIMEOUT_SECONDS", "15"))
    # Comma-separated tool names exposed to the agent; empty means all tools.
    mcp_tool_names: str = os.getenv(
        "MCP_TOOL_NAMES", "search_company,get_company,get_company_financials"
    )
    mcp_auth_token: str = os.getenv("MCP_AUTH_TOKEN", "")

    @property
    def mcp_tool_filter(self) -> list[str] | None:
        names = [name.strip() for name in self.mcp_tool_names.split(",") if name.strip()]
        return names or None
    score_threshold_approve: int = int(os.getenv("SCORE_THRESHOLD_APPROVE", "70"))
    score_threshold_review: int = int(os.getenv("SCORE_THRESHOLD_REVIEW", "40"))


settings = Settings()
