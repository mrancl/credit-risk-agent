"""Deterministic credit-risk scoring policy.

Starts from a neutral base score and applies bounded, auditable adjustments.
Factor groups:

- solvency:       insolvency flag, negative equity, leverage (I7/I10)
- profitability:  latest net profit, consecutive loss streak
- trend:          turnover trajectory over the last fiscal years
- liquidity:      current assets vs total liabilities (coverage approximation)
- stability:      company age, public-procurement exposure and concentration
- data quality:   missing core fields

Every factor emits both a RiskFactorScore and a RiskEvidence entry so each
point of the final score can be traced to a source value.
"""

from datetime import UTC, datetime

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


class _Scorecard:
    def __init__(self) -> None:
        self.score = 60.0
        self.factors: list[RiskFactorScore] = []
        self.evidence: list[RiskEvidence] = []
        self.ratios: dict[str, float | None] = {}

    def add(
        self,
        factor: str,
        impact: float,
        weight: float,
        rationale: str,
        source_field: str,
        value: object,
    ) -> None:
        self.score += impact
        self.factors.append(
            RiskFactorScore(factor=factor, score=impact, weight=weight, rationale=rationale)
        )
        self.evidence.append(
            RiskEvidence(
                factor=factor,
                source_field=source_field,
                value=str(value),
                rationale=rationale,
                impact=impact,
            )
        )


def _score_insolvency(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    impact = -45.0 if profile.insolvency_flag else 0.0
    card.add(
        "insolvency", impact, 1.0,
        "Insolvency is a critical default-risk indicator.",
        "insolvency_flag", profile.insolvency_flag,
    )


def _score_debt_to_state(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    impact = 0.0
    if profile.debt_to_state is not None:
        if profile.debt_to_state > 1_000_000:
            impact = -20.0
        elif profile.debt_to_state > 100_000:
            impact = -10.0
    card.add(
        "debt_to_state", impact, 0.8,
        "Higher debts to state increase repayment risk.",
        "debt_to_state", profile.debt_to_state,
    )


def _score_profitability(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    if profile.net_profit is None:
        impact, rationale = 0.0, "Net profit unavailable; profitability not assessed."
    elif profile.net_profit > 0:
        impact, rationale = 10.0, "Latest year is profitable, lowering short-term credit risk."
    else:
        impact, rationale = -8.0, "Latest year closed with a loss, raising short-term credit risk."
    card.add("profitability", impact, 0.5, rationale, "net_profit", profile.net_profit)

    # Consecutive loss years, newest first.
    streak = 0
    for year in reversed(profile.financial_history):
        if year.net_profit is None:
            break
        if year.net_profit < 0:
            streak += 1
        else:
            break
    streak_impact = -10.0 if streak >= 2 else 0.0
    card.add(
        "loss_streak", streak_impact, 0.7,
        "Two or more consecutive loss years signal structural problems.",
        "financial_history.net_profit", f"{streak} consecutive loss year(s)",
    )


def _score_turnover_trend(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    turnovers = [
        (year.year, year.turnover)
        for year in profile.financial_history
        if year.turnover is not None and year.turnover > 0
    ]
    if len(turnovers) < 3:
        card.add(
            "turnover_trend", 0.0, 0.6,
            "Not enough fiscal years to establish a turnover trend.",
            "financial_history.turnover", f"{len(turnovers)} usable year(s)",
        )
        return

    latest_year, latest = turnovers[-1]
    baseline_values = [value for _, value in turnovers[-4:-1]]
    baseline = sum(baseline_values) / len(baseline_values)
    change = (latest - baseline) / baseline
    card.ratios["turnover_change_vs_3y_avg"] = round(change, 4)

    if change >= 0.10:
        impact, label = 6.0, "growing"
    elif change <= -0.15:
        impact, label = -8.0, "declining"
    else:
        impact, label = 0.0, "stable"
    card.add(
        "turnover_trend", impact, 0.6,
        f"Turnover is {label} versus the prior-years average.",
        "financial_history.turnover",
        f"{latest_year}: {change:+.1%} vs 3y avg",
    )


def _score_balance_sheet(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    latest = profile.financial_history[-1] if profile.financial_history else None
    liabilities = latest.total_liabilities if latest else None
    equity = latest.total_equity if latest else None
    current_assets = latest.current_assets if latest else None

    # Leverage: total liabilities / total equity.
    if liabilities is None or equity is None:
        card.add(
            "leverage", 0.0, 0.7,
            "Balance-sheet data unavailable; leverage not assessed.",
            "financial_history", None,
        )
    elif equity <= 0:
        card.ratios["leverage"] = None
        card.add(
            "leverage", -15.0, 0.7,
            "Negative equity: liabilities exceed total assets.",
            "total_equity", equity,
        )
    else:
        ratio = liabilities / equity
        card.ratios["leverage"] = round(ratio, 2)
        if ratio > 4:
            impact, label = -10.0, "very high"
        elif ratio > 2:
            impact, label = -4.0, "elevated"
        elif ratio < 1:
            impact, label = 5.0, "low"
        else:
            impact, label = 0.0, "moderate"
        card.add(
            "leverage", impact, 0.7,
            f"Leverage (liabilities/equity) is {label}.",
            "total_liabilities/total_equity", f"{ratio:.2f}",
        )

    # Liquidity approximation: current assets / total liabilities.
    # Total (not current) liabilities is what the source exposes, so this
    # understates true current-ratio liquidity; thresholds account for that.
    if current_assets is None or liabilities is None or liabilities <= 0:
        card.add(
            "liquidity", 0.0, 0.5,
            "Liquidity data unavailable; not assessed.",
            "financial_history", None,
        )
    else:
        coverage = current_assets / liabilities
        card.ratios["current_assets_to_liabilities"] = round(coverage, 2)
        if coverage >= 1.2:
            impact, label = 4.0, "comfortable"
        elif coverage < 0.6:
            impact, label = -6.0, "tight"
        else:
            impact, label = 0.0, "adequate"
        card.add(
            "liquidity", impact, 0.5,
            f"Current assets cover total liabilities at a {label} level.",
            "current_assets/total_liabilities", f"{coverage:.2f}",
        )


def _score_company_age(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    reg = profile.registration_date or ""
    if len(reg) >= 4 and reg[:4].isdigit():
        age = datetime.now(UTC).year - int(reg[:4])
        if age < 2:
            impact, label = -6.0, "very young"
        elif age >= 10:
            impact, label = 4.0, "long-established"
        else:
            impact, label = 0.0, "established"
        card.add(
            "company_age", impact, 0.4,
            f"Company is {label} ({age} years since registration).",
            "registration_date", reg,
        )
    else:
        card.add(
            "company_age", 0.0, 0.4,
            "Registration date unavailable; age not assessed.",
            "registration_date", reg or None,
        )


def _score_public_contracts(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    contracts = profile.public_contracts
    if contracts is None:
        card.add(
            "public_contracts", 0.0, 0.3,
            "Public-procurement data not collected; not assessed.",
            "public_contracts", None,
        )
        return

    impact = 3.0 if contracts.contracts_as_supplier > 0 else 0.0
    card.add(
        "public_contracts", impact, 0.3,
        "Verified SEAP contracts as supplier are a stable revenue signal.",
        "public_contracts.contracts_as_supplier", contracts.contracts_as_supplier,
    )

    # Concentration: public contract value vs turnover in the latest year
    # with data on both sides.
    concentration = None
    for year in reversed(profile.financial_history):
        value = contracts.value_by_year.get(str(year.year))
        if value is not None and year.turnover:
            concentration = value / year.turnover
            card.ratios["public_revenue_share"] = round(concentration, 4)
            break

    if concentration is None:
        card.add(
            "state_dependency", 0.0, 0.4,
            "No overlapping year of contract values and turnover; concentration not assessed.",
            "public_contracts.value_by_year", contracts.value_by_year or None,
        )
        return

    if concentration > 0.5:
        impact, label = -6.0, "high"
    elif concentration > 0.2:
        impact, label = -2.0, "moderate"
    else:
        impact, label = 0.0, "low"
    card.add(
        "state_dependency", impact, 0.4,
        f"Dependency on public-procurement revenue is {label}.",
        "public_contracts/turnover", f"{concentration:.1%}",
    )


def _score_data_quality(card: _Scorecard, profile: CanonicalCompanyProfile) -> None:
    impact = -2.5 * len(profile.missing_fields)
    card.add(
        "data_quality", impact, 0.4,
        "Missing key fields reduce confidence and score.",
        "missing_fields",
        ", ".join(profile.missing_fields) if profile.missing_fields else "none",
    )


def evaluate_credit_risk(profile: CanonicalCompanyProfile) -> CreditRiskAssessment:
    card = _Scorecard()

    _score_insolvency(card, profile)
    _score_debt_to_state(card, profile)
    _score_profitability(card, profile)
    _score_turnover_trend(card, profile)
    _score_balance_sheet(card, profile)
    _score_company_age(card, profile)
    _score_public_contracts(card, profile)
    _score_data_quality(card, profile)

    bounded_score = max(0, min(100, int(round(card.score))))
    confidence = max(0.25, min(0.95, 1.0 - (0.1 * len(profile.missing_fields))))

    return CreditRiskAssessment(
        company_identifier=profile.company_identifier,
        legal_name=profile.legal_name,
        score=bounded_score,
        recommendation=_recommendation(bounded_score),
        confidence=confidence,
        factors=card.factors,
        evidence=card.evidence,
        audit={
            "policy": {
                "approve_threshold": settings.score_threshold_approve,
                "review_threshold": settings.score_threshold_review,
            },
            "ratios": card.ratios,
            "missing_fields": profile.missing_fields,
            "source": "demoanaf.ro/mcp",
        },
    )
