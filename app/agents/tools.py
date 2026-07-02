import json
from datetime import UTC, datetime
from typing import Any

from app.integrations.mcp_normalizer import normalize_company_payload
from app.risk.policy import evaluate_credit_risk


def _parse_json_if_possible(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    if not candidate:
        return value
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return value


def _extract_payload_dict(raw_response: Any) -> dict[str, Any]:
    parsed = _parse_json_if_possible(raw_response)

    if isinstance(parsed, dict):
        if isinstance(parsed.get("structuredContent"), dict):
            return parsed["structuredContent"]
        if isinstance(parsed.get("result"), dict):
            return parsed["result"]
        return parsed

    if isinstance(parsed, list):
        for item in parsed:
            candidate = _extract_payload_dict(item)
            if candidate:
                return candidate

    if hasattr(parsed, "model_dump"):
        return _extract_payload_dict(parsed.model_dump(mode="json", exclude_none=True))

    if hasattr(parsed, "text"):
        return _extract_payload_dict(getattr(parsed, "text"))

    raise ValueError("Unable to extract object payload from MCP tool response")


def evaluate_company_credit_risk_from_profile(
    company_identifier: str,
    company_profile: dict[str, Any] | str,
) -> str:
    """Score credit risk using a company profile returned by an MCP tool."""
    raw_payload = _extract_payload_dict(company_profile)
    profile = normalize_company_payload(company_identifier=company_identifier, raw_payload=raw_payload)
    assessment = evaluate_credit_risk(profile)

    quality_note = (
        "Data quality: high (all core fields present)."
        if not profile.missing_fields
        else f"Data quality: medium/low. Missing fields: {', '.join(profile.missing_fields)}"
    )

    result = assessment.model_dump()
    result["audit"]["evaluated_at_utc"] = datetime.now(UTC).isoformat()

    final = {
        "company_identifier": company_identifier,
        "legal_name": result.get("legal_name"),
        "caen_code": profile.caen_code,
        "score": result["score"],
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "quality_note": quality_note,
        "factors": result["factors"],
        "evidence": result["evidence"],
        "financial_history": [year.model_dump() for year in profile.financial_history],
        "public_contracts": (
            profile.public_contracts.model_dump() if profile.public_contracts else None
        ),
        "audit": result["audit"],
    }
    return json.dumps(final, ensure_ascii=True)
