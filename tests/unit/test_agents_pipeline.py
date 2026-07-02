import json

from app.agents import tools


def test_evaluate_company_credit_risk_from_profile() -> None:
    payload = tools.evaluate_company_credit_risk_from_profile(
        "RO999",
        {
            "denumire": "Demo Company SRL",
            "stare_fiscala": "active",
            "insolventa": False,
            "datorii_stat": 5000,
            "cifra_afaceri": 1200000,
            "profit_net": 80000,
            "numar_angajati": 12,
        },
    )
    result = json.loads(payload)

    assert result["company_identifier"] == "RO999"
    assert 0 <= result["score"] <= 100
    assert result["recommendation"] in {"approve", "review", "reject"}
    assert isinstance(result["evidence"], list)
    assert "policy" in result["audit"]
