from app.integrations.mcp_normalizer import normalize_company_payload


def _demoanaf_payload() -> dict:
    def year_entry(year: int, turnover: float, profit: float, loss: float = 0.0) -> dict:
        return {
            "year": year,
            "indicators": [
                {"code": "I13", "value": turnover},
                {"code": "I18", "value": profit},
                {"code": "I19", "value": loss},
                {"code": "I20", "value": 40},
                {"code": "I7", "value": 500_000},
                {"code": "I10", "value": 300_000},
                {"code": "I2", "value": 400_000},
                {"code": "I5", "value": 100_000},
            ],
        }

    return {
        "cui": 123,
        "name": "Multi Year SRL",
        "primaryCaen": "6201",
        "registrationDate": "2010-05-01",
        "inactive": False,
        "vatRegistered": True,
        "headquartersAddress": {"county": "Cluj"},
        "financials": {
            "years": [
                year_entry(2024, 900_000, 50_000),
                year_entry(2023, 800_000, 40_000),
                year_entry(2025, 1_000_000, 0, loss=60_000),  # out of order + loss year
            ]
        },
        "public_contracts": {
            "exists": True,
            "asSupplier": 3,
            "asAuthority": 0,
            "latestDate": "2025-11-10",
            "rows": [
                {"contractDate": "2025-03-01", "valueRon": 120_000},
                {"contractDate": "2025-09-15", "valueRon": 80_000},
                {"contractDate": "2024-01-20", "valueRon": 50_000},
            ],
        },
    }


def test_history_sorted_and_loss_year_negative() -> None:
    profile = normalize_company_payload("123", _demoanaf_payload())

    assert [y.year for y in profile.financial_history] == [2023, 2024, 2025]
    assert profile.financial_history[-1].net_profit == -60_000
    assert profile.financial_history[-1].total_liabilities == 500_000
    # Flat fields mirror the latest year.
    assert profile.turnover == 1_000_000
    assert profile.net_profit == -60_000
    assert profile.caen_code == "6201"


def test_public_contracts_aggregated_by_year() -> None:
    profile = normalize_company_payload("123", _demoanaf_payload())
    contracts = profile.public_contracts

    assert contracts is not None and contracts.has_contracts
    assert contracts.contracts_as_supplier == 3
    assert contracts.value_by_year == {"2025": 200_000.0, "2024": 50_000.0}
    assert contracts.total_value_ron == 250_000.0


def test_missing_contracts_block_is_none() -> None:
    payload = _demoanaf_payload()
    del payload["public_contracts"]
    profile = normalize_company_payload("123", payload)
    assert profile.public_contracts is None
