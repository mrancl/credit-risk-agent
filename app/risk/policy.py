from app.config import settings
from app.integrations.schema import (
    CanonicalCompanyProfile,
    CreditRiskAssessment,
    RiskEvidence,
    RiskFactorScore,
)


def _recommendation(score: int) -> str:
    if score >= settings.score_threshold_approve:
        return "approve"
    if score >= settings.score_threshold_review:
        return "review"
    return "reject"


def evaluate_credit_risk(profile: CanonicalCompanyProfile) -> CreditRiskAssessment:
    factors: list[RiskFactorScore] = []
    evidence: list[RiskEvidence] = []

    # Start neutral, then apply penalties/bonuses deterministically.
    score = 60.0

    insolvency_penalty = -45.0 if profile.insolvency_flag else 0.0
    score += insolvency_penalty
    factors.append(
        RiskFactorScore(
            factor="insolvency",
            score=insolvency_penalty,
            weight=1.0,
            rationale="Insolvency is a critical default-risk indicator.",
        )
    )
    evidence.append(
        RiskEvidence(
            factor="insolvency",
            source_field="insolvency_flag",
            value=str(profile.insolvency_flag),
            rationale="If insolvency is true, score receives a major penalty.",
            impact=insolvency_penalty,
        )
    )

    debt_penalty = 0.0
    if profile.debt_to_state is not None:
        if profile.debt_to_state > 1_000_000:
            debt_penalty = -20.0
        elif profile.debt_to_state > 100_000:
            debt_penalty = -10.0
    score += debt_penalty
    factors.append(
        RiskFactorScore(
            factor="debt_to_state",
            score=debt_penalty,
            weight=0.8,
            rationale="Higher debts to state increase repayment risk.",
        )
    )
    evidence.append(
        RiskEvidence(
            factor="debt_to_state",
            source_field="debt_to_state",
            value=str(profile.debt_to_state),
            rationale="Penalty bands based on debt amount.",
            impact=debt_penalty,
        )
    )

    profitability_impact = 0.0
    if profile.net_profit is not None:
        profitability_impact = 10.0 if profile.net_profit > 0 else -8.0
    score += profitability_impact
    factors.append(
        RiskFactorScore(
            factor="profitability",
            score=profitability_impact,
            weight=0.5,
            rationale="Profitable companies generally have lower short-term credit risk.",
        )
    )
    evidence.append(
        RiskEvidence(
            factor="profitability",
            source_field="net_profit",
            value=str(profile.net_profit),
            rationale="Positive net profit increases score, losses decrease score.",
            impact=profitability_impact,
        )
    )

    data_quality_penalty = -2.5 * len(profile.missing_fields)
    score += data_quality_penalty
    factors.append(
        RiskFactorScore(
            factor="data_quality",
            score=data_quality_penalty,
            weight=0.4,
            rationale="Missing key fields reduce confidence and score.",
        )
    )
    evidence.append(
        RiskEvidence(
            factor="data_quality",
            source_field="missing_fields",
            value=", ".join(profile.missing_fields) if profile.missing_fields else "none",
            rationale="Each missing critical field applies a small penalty.",
            impact=data_quality_penalty,
        )
    )

    bounded_score = max(0, min(100, int(round(score))))
    confidence = max(0.25, min(0.95, 1.0 - (0.1 * len(profile.missing_fields))))

    return CreditRiskAssessment(
        company_identifier=profile.company_identifier,
        legal_name=profile.legal_name,
        score=bounded_score,
        recommendation=_recommendation(bounded_score),
        confidence=confidence,
        factors=factors,
        evidence=evidence,
        audit={
            "policy": {
                "approve_threshold": settings.score_threshold_approve,
                "review_threshold": settings.score_threshold_review,
            },
            "missing_fields": profile.missing_fields,
            "source": "demoanaf.ro/mcp",
        },
    )
