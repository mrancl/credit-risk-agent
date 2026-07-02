from app.integrations.schema import (
    CanonicalCompanyProfile,
    PublicContractsSummary,
    YearFinancials,
)
from app.risk.policy import evaluate_credit_risk


def _year(year: int, turnover: float, profit: float, **kwargs) -> YearFinancials:
    return YearFinancials(year=year, turnover=turnover, net_profit=profit, **kwargs)


def _factor(result, name: str):
    return next(f for f in result.factors if f.factor == name)


def test_declining_turnover_and_loss_streak_penalized() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="1",
        legal_name="Declining SRL",
        net_profit=-50_000,
        turnover=400_000,
        financial_history=[
            _year(2022, 1_000_000, 100_000),
            _year(2023, 900_000, 20_000),
            _year(2024, 700_000, -30_000),
            _year(2025, 400_000, -50_000),
        ],
    )
    result = evaluate_credit_risk(profile)

    assert _factor(result, "turnover_trend").score < 0
    assert _factor(result, "loss_streak").score < 0


def test_growing_profitable_company_rewarded() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="2",
        legal_name="Growing SRL",
        net_profit=300_000,
        turnover=2_000_000,
        financial_history=[
            _year(2022, 1_000_000, 100_000),
            _year(2023, 1_200_000, 150_000),
            _year(2024, 1_500_000, 200_000),
            _year(2025, 2_000_000, 300_000),
        ],
    )
    result = evaluate_credit_risk(profile)

    assert _factor(result, "turnover_trend").score > 0
    assert _factor(result, "loss_streak").score == 0
    assert result.audit["ratios"]["turnover_change_vs_3y_avg"] > 0.1


def test_negative_equity_heavily_penalized() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="3",
        financial_history=[
            _year(2025, 500_000, -10_000, total_liabilities=800_000, total_equity=-50_000),
        ],
    )
    result = evaluate_credit_risk(profile)
    assert _factor(result, "leverage").score == -15.0


def test_leverage_and_liquidity_ratios_computed() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="4",
        financial_history=[
            _year(
                2025, 1_000_000, 50_000,
                total_liabilities=400_000, total_equity=600_000, current_assets=600_000,
            ),
        ],
    )
    result = evaluate_credit_risk(profile)

    assert result.audit["ratios"]["leverage"] == 0.67
    assert result.audit["ratios"]["current_assets_to_liabilities"] == 1.5
    assert _factor(result, "leverage").score > 0
    assert _factor(result, "liquidity").score > 0


def test_short_history_yields_neutral_trend() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="5",
        financial_history=[_year(2024, 100_000, 5_000), _year(2025, 90_000, 4_000)],
    )
    result = evaluate_credit_risk(profile)
    assert _factor(result, "turnover_trend").score == 0


def test_state_dependency_concentration() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="6",
        financial_history=[_year(2025, 1_000_000, 50_000)],
        public_contracts=PublicContractsSummary(
            has_contracts=True,
            contracts_as_supplier=12,
            value_by_year={"2025": 700_000.0},
            total_value_ron=700_000.0,
        ),
    )
    result = evaluate_credit_risk(profile)

    assert _factor(result, "public_contracts").score > 0  # supplier bonus
    assert _factor(result, "state_dependency").score == -6.0  # 70% of turnover
    assert result.audit["ratios"]["public_revenue_share"] == 0.7


def test_low_concentration_not_penalized() -> None:
    profile = CanonicalCompanyProfile(
        company_identifier="7",
        financial_history=[_year(2025, 10_000_000, 500_000)],
        public_contracts=PublicContractsSummary(
            has_contracts=True,
            contracts_as_supplier=3,
            value_by_year={"2025": 200_000.0},
        ),
    )
    result = evaluate_credit_risk(profile)
    assert _factor(result, "state_dependency").score == 0
