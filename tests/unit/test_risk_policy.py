from app.integrations.schema import CanonicalCompanyProfile
from app.risk.policy import evaluate_credit_risk


def test_policy_flags_insolvency_as_high_risk() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="RO123",
        legal_name="Risky SRL",
        insolvency_flag=True,
        debt_to_state=1_200_000,
        turnover=500_000,
        net_profit=-20_000,
    )

    result = evaluate_credit_risk(profile)

    assert result.score < 40
    assert result.recommendation == "reject"


def test_policy_rewards_profitable_company_with_low_debt() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="RO456",
        legal_name="Stable SRL",
        insolvency_flag=False,
        debt_to_state=10_000,
        turnover=5_000_000,
        net_profit=350_000,
        fiscal_status="active",
    )

    result = evaluate_credit_risk(profile)

    assert result.score >= 60
    assert result.recommendation in {"approve", "review"}
    assert result.confidence > 0.5
