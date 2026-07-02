from app.integrations.schema import CanonicalCompanyProfile


def _read_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "insolventa", "insolvent"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _get_first(raw: dict, keys: list[str]) -> object | None:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def normalize_company_payload(company_identifier: str, raw_payload: dict) -> CanonicalCompanyProfile:
    legal_name = _get_first(raw_payload, ["denumire", "name", "legal_name", "nume"])  # ANAF variants
    fiscal_status = _get_first(raw_payload, ["stare_fiscala", "fiscal_status", "status"])  # ANAF variants
    vat_status = _get_first(raw_payload, ["status_tva", "vat_status"])
    registration_date = _get_first(raw_payload, ["data_inregistrare", "registration_date"])
    county = _get_first(raw_payload, ["judet", "county"])

    debt_to_state = _get_first(raw_payload, ["datorii_stat", "debt_to_state", "debts"])
    turnover = _get_first(raw_payload, ["cifra_afaceri", "turnover"])
    net_profit = _get_first(raw_payload, ["profit_net", "net_profit"])
    employee_count = _get_first(raw_payload, ["numar_angajati", "employee_count"])

    insolvency_raw = _get_first(raw_payload, ["insolventa", "insolvency", "insolvency_flag"])

    profile = CanonicalCompanyProfile(
        company_identifier=company_identifier,
        legal_name=str(legal_name) if legal_name is not None else None,
        fiscal_status=str(fiscal_status) if fiscal_status is not None else None,
        vat_status=str(vat_status) if vat_status is not None else None,
        registration_date=str(registration_date) if registration_date is not None else None,
        county=str(county) if county is not None else None,
        insolvency_flag=_read_bool(insolvency_raw),
        debt_to_state=float(debt_to_state) if debt_to_state not in (None, "") else None,
        turnover=float(turnover) if turnover not in (None, "") else None,
        net_profit=float(net_profit) if net_profit not in (None, "") else None,
        employee_count=int(employee_count) if employee_count not in (None, "") else None,
        source_payload=raw_payload,
    )

    missing_fields: list[str] = []
    if profile.legal_name is None:
        missing_fields.append("legal_name")
    if profile.fiscal_status is None:
        missing_fields.append("fiscal_status")
    if profile.turnover is None:
        missing_fields.append("turnover")
    if profile.net_profit is None:
        missing_fields.append("net_profit")

    profile.missing_fields = missing_fields
    return profile
