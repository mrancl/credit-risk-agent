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


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _indicator_map(year_entry: dict) -> dict[str, float]:
    """Flatten a DemoANAF financials year entry's indicator list by code."""
    out: dict[str, float] = {}
    for indicator in year_entry.get("indicators", []) or []:
        code = indicator.get("code")
        value = _to_float(indicator.get("value"))
        if code and value is not None:
            out[code] = value
    return out


def _extract_latest_financials(raw: dict) -> dict[str, object]:
    """Pull turnover / net profit / employees from DemoANAF financials.

    DemoANAF (get_company and get_company_financials) reports balance-sheet
    data as coded indicators per year: I13 net turnover, I18 net profit,
    I19 net loss, I20 average employees. Uses the most recent year that
    reports a turnover figure.
    """
    financials = raw.get("financials") if isinstance(raw.get("financials"), dict) else raw
    years = financials.get("years") if isinstance(financials, dict) else None
    if not isinstance(years, list):
        return {}

    best_year: int | None = None
    best: dict[str, float] = {}
    for entry in years:
        if not isinstance(entry, dict):
            continue
        indicators = _indicator_map(entry)
        year = entry.get("year")
        if "I13" not in indicators or not isinstance(year, int):
            continue
        if best_year is None or year > best_year:
            best_year = year
            best = indicators

    if best_year is None:
        return {}

    net_profit = best.get("I18", 0.0)
    net_loss = best.get("I19", 0.0)
    if net_profit == 0.0 and net_loss > 0.0:
        net_profit = -net_loss

    result: dict[str, object] = {
        "turnover": best.get("I13"),
        "net_profit": net_profit,
        "financials_year": best_year,
    }
    if "I20" in best:
        result["employee_count"] = int(best["I20"])
    return result


def _derive_fiscal_status(raw: dict) -> object | None:
    explicit = _get_first(raw, ["stare_fiscala", "fiscal_status", "onrcStatusLabel", "registrationState"])
    if explicit is not None:
        return explicit
    inactive = raw.get("inactive")
    if isinstance(inactive, bool):
        return "inactive" if inactive else "active"
    return _get_first(raw, ["status"])


def _derive_vat_status(raw: dict) -> object | None:
    # Note: DemoANAF's "vatStatus" field is data freshness, not VAT standing.
    explicit = _get_first(raw, ["status_tva", "vat_status"])
    if explicit is not None:
        return explicit
    vat_registered = raw.get("vatRegistered")
    if isinstance(vat_registered, bool):
        return "registered" if vat_registered else "not_registered"
    return None


def _derive_county(raw: dict) -> object | None:
    explicit = _get_first(raw, ["judet", "county"])
    if explicit is not None:
        return explicit
    headquarters = raw.get("headquartersAddress")
    if isinstance(headquarters, dict):
        return headquarters.get("county")
    return None


def _derive_insolvency(raw: dict) -> bool:
    explicit = _get_first(raw, ["insolventa", "insolvency", "insolvency_flag"])
    if explicit is not None:
        return _read_bool(explicit)
    # Fall back to ONRC status text, e.g. "Insolvență" / "în insolvență".
    for key in ("onrcStatusLabel", "registrationState"):
        value = raw.get(key)
        if isinstance(value, str) and "insolven" in value.lower():
            return True
    return False


def normalize_company_payload(company_identifier: str, raw_payload: dict) -> CanonicalCompanyProfile:
    legal_name = _get_first(raw_payload, ["denumire", "name", "legal_name", "nume"])  # ANAF variants
    fiscal_status = _derive_fiscal_status(raw_payload)
    vat_status = _derive_vat_status(raw_payload)
    registration_date = _get_first(
        raw_payload, ["data_inregistrare", "registration_date", "registrationDate"]
    )
    county = _derive_county(raw_payload)

    debt_to_state = _get_first(raw_payload, ["datorii_stat", "debt_to_state", "debts"])
    turnover = _get_first(raw_payload, ["cifra_afaceri", "turnover"])
    net_profit = _get_first(raw_payload, ["profit_net", "net_profit"])
    employee_count = _get_first(raw_payload, ["numar_angajati", "employee_count"])

    financials = _extract_latest_financials(raw_payload)
    if turnover is None:
        turnover = financials.get("turnover")
    if net_profit is None:
        net_profit = financials.get("net_profit")
    if employee_count is None:
        employee_count = financials.get("employee_count")

    profile = CanonicalCompanyProfile(
        company_identifier=company_identifier,
        legal_name=str(legal_name) if legal_name is not None else None,
        fiscal_status=str(fiscal_status) if fiscal_status is not None else None,
        vat_status=str(vat_status) if vat_status is not None else None,
        registration_date=str(registration_date) if registration_date is not None else None,
        county=str(county) if county is not None else None,
        insolvency_flag=_derive_insolvency(raw_payload),
        debt_to_state=_to_float(debt_to_state),
        turnover=_to_float(turnover),
        net_profit=_to_float(net_profit),
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
